"""Pick a free IPv4 address in the homelab pool and reserve it in Pi-hole.

The Pi-hole ``dns.hosts`` record *is* the reservation: an address is taken as
soon as any FQDN points to it. On top of that, an optional liveness probe
(ICMP) protects against hosts that exist on the LAN without a DNS record.
"""

from __future__ import annotations

import ipaddress
import platform
import subprocess
from dataclasses import dataclass
from typing import Iterable, Iterator, Protocol

from . import const
from .environment import Environment
from .errors import FixedIpError, NoFreeIpError
from .pihole_client import DnsHostRecord, DnsHostsBackend


# ---------------------------------------------------------------------------
# Pool
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IpPool:
    """Inclusive IPv4 range with a set of addresses that are never allocated."""

    start: ipaddress.IPv4Address
    end: ipaddress.IPv4Address
    reserved: frozenset[ipaddress.IPv4Address] = frozenset()

    @classmethod
    def from_strings(
        cls,
        start: str = const.IP_POOL_DEFAULT_START,
        end: str = const.IP_POOL_DEFAULT_END,
        reserved: Iterable[str] = const.IP_POOL_DEFAULT_RESERVED,
    ) -> "IpPool":
        pool = cls(
            start=ipaddress.IPv4Address(start),
            end=ipaddress.IPv4Address(end),
            reserved=frozenset(ipaddress.IPv4Address(r) for r in reserved if r),
        )
        if pool.start > pool.end:
            raise ValueError(f"Pool start {start} is after end {end}")
        return pool

    def __iter__(self) -> Iterator[ipaddress.IPv4Address]:
        current = self.start
        while current <= self.end:
            yield current
            current += 1

    def __contains__(self, ip: object) -> bool:
        return isinstance(ip, ipaddress.IPv4Address) and self.start <= ip <= self.end

    def is_reserved(self, ip: ipaddress.IPv4Address) -> bool:
        return ip in self.reserved


# ---------------------------------------------------------------------------
# Liveness probes
# ---------------------------------------------------------------------------


class LivenessProbe(Protocol):
    def is_alive(self, ip: ipaddress.IPv4Address) -> bool: ...


class NoProbe:
    """Trust Pi-hole only (used in tests or when ICMP is blocked)."""

    def is_alive(self, ip: ipaddress.IPv4Address) -> bool:  # noqa: ARG002
        return False


class IcmpProbe:
    """Single ICMP echo; a reply means the address is in use."""

    def __init__(self, timeout_s: int = const.PING_TIMEOUT_S) -> None:
        self._timeout_s = timeout_s

    def is_alive(self, ip: ipaddress.IPv4Address) -> bool:
        # `-W` is the per-reply timeout on both Linux (seconds) and macOS (ms).
        timeout_value = self._timeout_s * 1000 if platform.system() == "Darwin" else self._timeout_s
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", str(timeout_value), str(ip)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self._timeout_s + 2,
                check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
        return result.returncode == 0


# ---------------------------------------------------------------------------
# Allocator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Allocation:
    ip: str
    fqdn: str
    reused: bool

    def to_dotenv(self, env: Environment | None = None) -> str:
        """GitLab dotenv lines, keys prefixed by the environment (``PROD_VM_IP``, ...)."""
        env = env or Environment.default()
        return "\n".join(
            [
                f"{env.vm_ip_key}={self.ip}",
                f"{env.fqdn_key}={self.fqdn}",
                f"{env.ip_reused_key}={'true' if self.reused else 'false'}",
                "",
            ]
        )


class IpAllocator:
    """Allocate / release an address for a given FQDN.

    Resolution order in :meth:`allocate` when ``fixed_ip`` is empty:

    1. A record for ``fqdn`` already exists -> reuse it (idempotent re-runs).
    2. ``pinned_ip`` is given and free -> reserve it.
    3. First address of the pool that has no record, is not reserved and does
       not answer the liveness probe -> reserve it.

    When ``fixed_ip`` is set, the pool is not scanned. The FQDN is pointed at
    that address, or the call fails if another name already owns it.
    """

    def __init__(
        self,
        backend: DnsHostsBackend,
        pool: IpPool,
        probe: LivenessProbe | None = None,
    ) -> None:
        self._backend = backend
        self._pool = pool
        self._probe = probe or NoProbe()

    def allocate(
        self,
        fqdn: str,
        pinned_ip: str | None = None,
        fixed_ip: str | None = None,
    ) -> Allocation:
        records = self._backend.list_hosts()
        if fixed_ip:
            return self._assign_fixed(records, fqdn, fixed_ip)

        existing = self._find_by_fqdn(records, fqdn)
        if existing is not None:
            return Allocation(ip=existing.ip, fqdn=fqdn, reused=True)

        used = {ipaddress.IPv4Address(r.ip) for r in records if self._is_ipv4(r.ip)}

        candidates: list[ipaddress.IPv4Address] = []
        if pinned_ip:
            candidates.append(ipaddress.IPv4Address(pinned_ip))
        candidates.extend(ip for ip in self._pool if ip not in candidates)

        for ip in candidates:
            if ip in used or self._pool.is_reserved(ip):
                continue
            if self._probe.is_alive(ip):
                continue
            self._backend.add_host(DnsHostRecord(ip=str(ip), domain=fqdn))
            return Allocation(ip=str(ip), fqdn=fqdn, reused=False)

        raise NoFreeIpError(
            f"No free address for {fqdn} in {self._pool.start}-{self._pool.end}"
        )

    def _assign_fixed(self, records: Iterable[DnsHostRecord], fqdn: str, fixed_ip: str) -> Allocation:
        """Point ``fqdn`` at ``fixed_ip`` without scanning the pool."""
        ip = str(ipaddress.IPv4Address(fixed_ip))
        wanted = fqdn.lower().rstrip(".")
        for record in records:
            if record.ip == ip and record.domain.lower().rstrip(".") != wanted:
                raise FixedIpError(
                    f"{ip} is already used by {record.domain}; not assigning it to {fqdn}"
                )

        existing = self._find_by_fqdn(records, fqdn)
        if existing is not None and existing.ip == ip:
            return Allocation(ip=ip, fqdn=fqdn, reused=True)
        if existing is not None:
            self._backend.delete_host(existing)
        self._backend.add_host(DnsHostRecord(ip=ip, domain=fqdn))
        return Allocation(ip=ip, fqdn=fqdn, reused=False)

    def release(self, fqdn: str) -> DnsHostRecord | None:
        """Remove the record for ``fqdn``. Returns it, or ``None`` if absent."""
        existing = self._find_by_fqdn(self._backend.list_hosts(), fqdn)
        if existing is None:
            return None
        self._backend.delete_host(existing)
        return existing

    @staticmethod
    def _find_by_fqdn(records: Iterable[DnsHostRecord], fqdn: str) -> DnsHostRecord | None:
        wanted = fqdn.lower().rstrip(".")
        for record in records:
            if record.domain.lower().rstrip(".") == wanted:
                return record
        return None

    @staticmethod
    def _is_ipv4(value: str) -> bool:
        try:
            ipaddress.IPv4Address(value)
        except ipaddress.AddressValueError:
            return False
        return True
