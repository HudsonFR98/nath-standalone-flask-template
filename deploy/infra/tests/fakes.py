"""In-memory doubles shared by the infra tests."""

from __future__ import annotations

import ipaddress

from ..pihole_client import DnsHostRecord


class FakePihole:
    """Implements `DnsHostsBackend` on top of a list."""

    def __init__(self, records: list[DnsHostRecord] | None = None) -> None:
        self.records: list[DnsHostRecord] = list(records or [])
        self.added: list[DnsHostRecord] = []
        self.deleted: list[DnsHostRecord] = []

    def list_hosts(self) -> list[DnsHostRecord]:
        return list(self.records)

    def add_host(self, record: DnsHostRecord) -> None:
        self.records.append(record)
        self.added.append(record)

    def delete_host(self, record: DnsHostRecord) -> None:
        self.records.remove(record)
        self.deleted.append(record)


class FakeProbe:
    """Reports the given addresses as alive."""

    def __init__(self, alive: tuple[str, ...] = ()) -> None:
        self._alive = {ipaddress.IPv4Address(ip) for ip in alive}
        self.probed: list[ipaddress.IPv4Address] = []

    def is_alive(self, ip: ipaddress.IPv4Address) -> bool:
        self.probed.append(ip)
        return ip in self._alive
