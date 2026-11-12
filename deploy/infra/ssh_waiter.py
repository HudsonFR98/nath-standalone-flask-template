"""Block until a host is ready for Ansible.

Two stages:

1. :class:`SshWaiter` polls TCP/22 until sshd sends its banner.
2. :class:`CloudInitWaiter` (optional) runs ``cloud-init status --wait`` over
   SSH so that users, keys and network are fully configured before the deploy
   stage starts.

Cloud-init needs a minute or two after Terraform reports the VM as started;
the deploy stage must not run Ansible before that.
"""

from __future__ import annotations

import socket
import subprocess
import time
from typing import Callable

from . import const
from .errors import SshTimeoutError


class SshWaiter:
    def __init__(
        self,
        host: str,
        port: int = const.SSH_PORT,
        timeout_s: int = const.SSH_WAIT_DEFAULT_TIMEOUT_S,
        interval_s: int = const.SSH_WAIT_DEFAULT_INTERVAL_S,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        connector: Callable[[str, int, float], bool] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout_s = timeout_s
        self._interval_s = interval_s
        self._clock = clock
        self._sleep = sleep
        self._connect = connector or self._tcp_connect

    def wait(self) -> float:
        """Return the elapsed seconds once SSH is reachable, or raise."""
        started = self._clock()
        deadline = started + self._timeout_s
        while True:
            if self._connect(self._host, self._port, float(self._interval_s)):
                return self._clock() - started
            if self._clock() >= deadline:
                raise SshTimeoutError(
                    f"{self._host}:{self._port} did not accept SSH within {self._timeout_s}s"
                )
            self._sleep(self._interval_s)

    @staticmethod
    def _tcp_connect(host: str, port: int, timeout_s: float) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout_s) as sock:
                # sshd greets with its banner; reading it proves the daemon is up,
                # not just that the kernel accepted the connection.
                sock.settimeout(timeout_s)
                banner = sock.recv(64)
                return banner.startswith(b"SSH-")
        except (OSError, socket.timeout):
            return False


class CloudInitWaiter:
    """Run ``cloud-init status --wait`` through SSH until it reports completion.

    Exit code semantics of ``cloud-init status``: 0 = done, 2 = done with
    recoverable errors (accepted, logged), 1 = error/not finished, 255 = ssh
    itself failed (host not ready yet). Anything but 0/2 is retried until the
    deadline.
    """

    def __init__(
        self,
        host: str,
        user: str,
        key_path: str,
        port: int = const.SSH_PORT,
        timeout_s: int = const.SSH_WAIT_DEFAULT_TIMEOUT_S,
        interval_s: int = const.SSH_WAIT_DEFAULT_INTERVAL_S,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        runner: Callable[[list[str], float], int] | None = None,
        log: Callable[[str], None] = print,
    ) -> None:
        self._host = host
        self._user = user
        self._key_path = key_path
        self._port = port
        self._timeout_s = timeout_s
        self._interval_s = interval_s
        self._clock = clock
        self._sleep = sleep
        self._run = runner or self._run_subprocess
        self._log = log

    def command(self) -> list[str]:
        return [
            "ssh",
            "-p", str(self._port),
            "-i", self._key_path,
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"ConnectTimeout={self._interval_s}",
            f"{self._user}@{self._host}",
            "cloud-init status --wait",
        ]

    def wait(self) -> float:
        started = self._clock()
        deadline = started + self._timeout_s
        while True:
            remaining = max(deadline - self._clock(), 1.0)
            rc = self._run(self.command(), remaining)
            if rc in const.CLOUD_INIT_DONE_EXIT_CODES:
                if rc != 0:
                    self._log(f"cloud-init finished with recoverable errors (exit {rc})")
                return self._clock() - started
            if self._clock() >= deadline:
                raise SshTimeoutError(
                    f"cloud-init on {self._user}@{self._host} not done within {self._timeout_s}s (last exit {rc})"
                )
            self._sleep(self._interval_s)

    @staticmethod
    def _run_subprocess(cmd: list[str], timeout_s: float) -> int:
        try:
            return subprocess.run(cmd, timeout=timeout_s, check=False).returncode
        except subprocess.TimeoutExpired:
            return 1
