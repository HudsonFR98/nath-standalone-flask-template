#!/usr/bin/env python3
"""CLI used by the `infra` stage of .gitlab-ci.yml.

Sub-commands
------------
allocate-ip      Reserve (or reuse) an IP for an FQDN in Pi-hole; write dotenv.
release-ip       Remove the Pi-hole record of an FQDN (manual destroy job).
next-generation  Compute the VM generation from `terraform show -json` output.
guard-plan       Fail if `terraform show -json tfplan` deletes/replaces the VM.
wait-ssh         Block until a host answers on TCP/22 with an SSH banner.

Every sub-command that writes a dotenv file takes `--env <name>` (integration,
validation, prod); the keys are prefixed with the upper-cased name
(`INTEGRATION_VM_IP`, `PROD_VM_IP`, ...) so one pipeline can carry several
environments.

Secrets are read from environment variables only (never from argv), so they do
not leak into the job log:
  PIHOLE_APP_PASSWORD   Pi-hole application password
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from infra import const  # noqa: E402
from infra.environment import Environment  # noqa: E402
from infra.errors import InfraError  # noqa: E402
from infra.generation import GenerationResolver, StateSnapshot  # noqa: E402
from infra.ip_allocator import IcmpProbe, IpAllocator, IpPool, NoProbe  # noqa: E402
from infra.pihole_client import PiholeClient  # noqa: E402
from infra.plan_guard import TerraformPlanGuard  # noqa: E402
from infra.ssh_waiter import CloudInitWaiter, SshWaiter  # noqa: E402

EXIT_OK = 0
EXIT_INFRA_ERROR = 2
EXIT_USAGE = 64


class InfraCli:
    """Argument parsing and dispatch; each `cmd_*` method is one sub-command."""

    def __init__(self, stdout=sys.stdout, stderr=sys.stderr) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self._parser = self._build_parser()

    # -- entry point -----------------------------------------------------------

    def run(self, argv: list[str] | None = None) -> int:
        args = self._parser.parse_args(argv)
        try:
            return args.handler(args)
        except InfraError as exc:
            self._err(f"error: {exc}")
            return EXIT_INFRA_ERROR
        except (ValueError, OSError) as exc:
            self._err(f"error: {exc}")
            return EXIT_USAGE

    # -- sub-commands ----------------------------------------------------------

    def cmd_allocate_ip(self, args: argparse.Namespace) -> int:
        password = self._require_env("PIHOLE_APP_PASSWORD")
        env = Environment(args.env)
        reserved = self._split_csv(args.reserved)
        # CI passes "" when the optional pool variables are unset: fall back to the defaults.
        pool = IpPool.from_strings(
            args.pool_start or const.IP_POOL_DEFAULT_START,
            args.pool_end or const.IP_POOL_DEFAULT_END,
            reserved,
        )
        probe = NoProbe() if args.no_ping else IcmpProbe()
        with PiholeClient(args.pihole_url, password) as pihole:
            allocation = IpAllocator(pihole, pool, probe).allocate(
                args.fqdn,
                args.pinned_ip or None,
                args.fixed_ip or None,
            )

        Path(args.output).write_text(allocation.to_dotenv(env), encoding="utf-8")
        verb = "Reusing" if allocation.reused else "Reserved"
        self._out(f"[{env}] {verb} {allocation.ip} for {allocation.fqdn} (written to {args.output})")
        return EXIT_OK

    def cmd_release_ip(self, args: argparse.Namespace) -> int:
        password = self._require_env("PIHOLE_APP_PASSWORD")
        pool = IpPool.from_strings()
        with PiholeClient(args.pihole_url, password) as pihole:
            removed = IpAllocator(pihole, pool).release(args.fqdn)
        if removed is None:
            self._out(f"No Pi-hole record for {args.fqdn}; nothing to release")
        else:
            self._out(f"Released {removed.ip} ({removed.domain}) from Pi-hole")
        return EXIT_OK

    def cmd_next_generation(self, args: argparse.Namespace) -> int:
        payload = self._read_input(args.state_json)
        snapshot = StateSnapshot.from_show_json(payload)
        generation = GenerationResolver(seed=args.seed).resolve(snapshot)
        if args.output:
            key = Environment(args.env).generation_key
            Path(args.output).write_text(f"{key}={generation}\n", encoding="utf-8")
        self._out(str(generation))
        return EXIT_OK

    def cmd_guard_plan(self, args: argparse.Namespace) -> int:
        payload = self._read_input(args.plan_json)
        TerraformPlanGuard(args.protect).check(payload)
        self._out("Plan guard: no destructive change on protected resources")
        return EXIT_OK

    def cmd_wait_ssh(self, args: argparse.Namespace) -> int:
        elapsed = SshWaiter(args.host, args.port, args.timeout, args.interval).wait()
        self._out(f"SSH ready on {args.host}:{args.port} after {elapsed:.0f}s")
        if args.cloud_init_wait:
            if not args.key:
                raise ValueError("--key is required with --cloud-init-wait")
            remaining = max(args.timeout - int(elapsed), args.interval)
            elapsed_ci = CloudInitWaiter(
                args.host, args.user, args.key, args.port, remaining, args.interval, log=self._out
            ).wait()
            self._out(f"cloud-init done on {args.user}@{args.host} after {elapsed_ci:.0f}s")
        return EXIT_OK

    # -- parser ----------------------------------------------------------------

    def _build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="infra_deploy.py", description=__doc__.split("\n\n")[0])
        sub = parser.add_subparsers(dest="command", required=True)

        allocate = sub.add_parser("allocate-ip", help="reserve or reuse an IP for an FQDN in Pi-hole")
        self._add_pihole_args(allocate)
        self._add_env_arg(allocate)
        allocate.add_argument("--fqdn", required=True)
        allocate.add_argument("--pool-start", default=const.IP_POOL_DEFAULT_START, help="empty = default")
        allocate.add_argument("--pool-end", default=const.IP_POOL_DEFAULT_END, help="empty = default")
        allocate.add_argument(
            "--reserved",
            action="append",
            default=list(const.IP_POOL_DEFAULT_RESERVED),
            help="address inside the pool to skip (repeatable or comma-separated)",
        )
        allocate.add_argument("--pinned-ip", default=None, help="preferred address if free")
        allocate.add_argument(
            "--fixed-ip",
            default=None,
            help="use this address exactly and do not scan the pool (empty = allocate)",
        )
        allocate.add_argument("--no-ping", action="store_true", help="skip the ICMP liveness probe")
        allocate.add_argument("--output", default="infra.env", help="dotenv file to write")
        allocate.set_defaults(handler=self.cmd_allocate_ip)

        release = sub.add_parser("release-ip", help="remove the Pi-hole record for an FQDN")
        self._add_pihole_args(release)
        release.add_argument("--fqdn", required=True)
        release.set_defaults(handler=self.cmd_release_ip)

        generation = sub.add_parser("next-generation", help="compute the VM generation from state")
        self._add_env_arg(generation)
        generation.add_argument("--state-json", default="-", help="`terraform show -json` output file, or - for stdin")
        generation.add_argument("--seed", type=int, default=const.GENERATION_DEFAULT_SEED)
        generation.add_argument("--output", default=None, help="optional dotenv file to write")
        generation.set_defaults(handler=self.cmd_next_generation)

        guard = sub.add_parser("guard-plan", help="fail on delete/replace of protected resources")
        guard.add_argument("--plan-json", default="-", help="`terraform show -json tfplan` file, or - for stdin")
        guard.add_argument(
            "--protect",
            action="append",
            default=[const.TERRAFORM_VM_RESOURCE_ADDRESS],
            help="resource address to protect (repeatable)",
        )
        guard.set_defaults(handler=self.cmd_guard_plan)

        wait = sub.add_parser("wait-ssh", help="wait until sshd answers on a host")
        wait.add_argument("--host", required=True)
        wait.add_argument("--port", type=int, default=const.SSH_PORT)
        wait.add_argument("--timeout", type=int, default=const.SSH_WAIT_DEFAULT_TIMEOUT_S)
        wait.add_argument("--interval", type=int, default=const.SSH_WAIT_DEFAULT_INTERVAL_S)
        wait.add_argument(
            "--cloud-init-wait",
            action="store_true",
            help="after TCP/22 answers, run `cloud-init status --wait` over SSH until done",
        )
        wait.add_argument("--user", default=const.SSH_DEFAULT_USER, help="SSH user for --cloud-init-wait")
        wait.add_argument("--key", default=None, help="private key path for --cloud-init-wait")
        wait.set_defaults(handler=self.cmd_wait_ssh)

        return parser

    @staticmethod
    def _add_pihole_args(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--pihole-url",
            default=os.environ.get("PIHOLE_URL", const.PIHOLE_DEFAULT_URL),
            help="Pi-hole base URL (default: $PIHOLE_URL or %(default)s)",
        )

    @staticmethod
    def _add_env_arg(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--env",
            default=const.DEFAULT_ENVIRONMENT,
            help="environment name used as dotenv key prefix: %s or an ad-hoc name such as sandbox (default: %%(default)s)"
            % "/".join(const.ENVIRONMENTS),
        )

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _require_env(name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise ValueError(f"environment variable {name} is required")
        return value

    @staticmethod
    def _split_csv(values: list[str]) -> list[str]:
        """`--reserved a --reserved b,c` and `--reserved ""` -> ['a', 'b', 'c']."""
        return [item.strip() for value in values for item in value.split(",") if item.strip()]

    @staticmethod
    def _read_input(path: str) -> str:
        if path == "-":
            return sys.stdin.read()
        return Path(path).read_text(encoding="utf-8")

    def _out(self, message: str) -> None:
        print(message, file=self._stdout)

    def _err(self, message: str) -> None:
        print(message, file=self._stderr)


def main(argv: list[str] | None = None) -> int:
    return InfraCli().run(argv)


if __name__ == "__main__":
    sys.exit(main())
