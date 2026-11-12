import unittest

from ..errors import SshTimeoutError
from ..ssh_waiter import CloudInitWaiter, SshWaiter


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


class SshWaiterTests(unittest.TestCase):
    def _waiter(self, results, timeout_s=30, interval_s=5):
        clock = FakeClock()
        answers = iter(results)

        def connector(_host, _port, _timeout):
            return next(answers)

        waiter = SshWaiter(
            "vm.lan", timeout_s=timeout_s, interval_s=interval_s, clock=clock, sleep=clock.sleep, connector=connector
        )
        return waiter, clock

    def test_returns_immediately_when_up(self):
        waiter, clock = self._waiter([True])
        self.assertEqual(waiter.wait(), 0.0)
        self.assertEqual(clock.slept, [])

    def test_retries_until_up(self):
        waiter, clock = self._waiter([False, False, True])
        self.assertEqual(waiter.wait(), 10.0)
        self.assertEqual(clock.slept, [5, 5])

    def test_times_out(self):
        waiter, _ = self._waiter([False] * 100, timeout_s=12, interval_s=5)
        with self.assertRaises(SshTimeoutError):
            waiter.wait()


class CloudInitWaiterTests(unittest.TestCase):
    def _waiter(self, exit_codes, timeout_s=30, interval_s=5):
        clock = FakeClock()
        codes = iter(exit_codes)
        logs = []
        commands = []

        def runner(cmd, _timeout):
            commands.append(cmd)
            return next(codes)

        waiter = CloudInitWaiter(
            "192.168.1.130", "Nath", "/tmp/key", timeout_s=timeout_s, interval_s=interval_s,
            clock=clock, sleep=clock.sleep, runner=runner, log=logs.append,
        )
        return waiter, clock, logs, commands

    def test_command_targets_user_host_with_batch_mode(self):
        waiter, *_ = self._waiter([0])
        cmd = waiter.command()
        self.assertEqual(cmd[0], "ssh")
        self.assertIn("Nath@192.168.1.130", cmd)
        self.assertIn("BatchMode=yes", cmd)
        self.assertIn("StrictHostKeyChecking=accept-new", cmd)
        self.assertEqual(cmd[-1], "cloud-init status --wait")

    def test_done_on_first_try(self):
        waiter, clock, logs, commands = self._waiter([0])
        self.assertEqual(waiter.wait(), 0.0)
        self.assertEqual(len(commands), 1)
        self.assertEqual(logs, [])

    def test_retries_while_ssh_refused_then_accepts_recoverable(self):
        waiter, clock, logs, _ = self._waiter([255, 1, 2])
        self.assertEqual(waiter.wait(), 10.0)
        self.assertEqual(clock.slept, [5, 5])
        self.assertEqual(len(logs), 1)
        self.assertIn("recoverable", logs[0])

    def test_times_out(self):
        waiter, *_ = self._waiter([1] * 100, timeout_s=12, interval_s=5)
        with self.assertRaises(SshTimeoutError):
            waiter.wait()


if __name__ == "__main__":
    unittest.main()
