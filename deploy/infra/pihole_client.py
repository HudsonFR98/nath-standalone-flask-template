"""Minimal Pi-hole v6 REST client for local DNS host records.

Only the endpoints needed by the pipeline are implemented:

* ``POST   /api/auth``                     -> open a session (sid + csrf)
* ``DELETE /api/auth``                     -> close it
* ``GET    /api/config/dns/hosts``         -> list ``"<ip> <domain>"`` records
* ``PUT    /api/config/dns/hosts/<value>`` -> add one record
* ``DELETE /api/config/dns/hosts/<value>`` -> remove one record
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Iterable, Protocol

from . import const
from .errors import PiholeAuthError, PiholeError


@dataclass(frozen=True)
class DnsHostRecord:
    """One entry of Pi-hole's ``dns.hosts`` list (``"192.168.1.130 host.lan"``)."""

    ip: str
    domain: str

    @classmethod
    def parse(cls, raw: str) -> "DnsHostRecord":
        parts = raw.split()
        if len(parts) < 2:
            raise PiholeError(f"Malformed dns.hosts entry: {raw!r}")
        # Pi-hole allows several domains per line; we only manage single-domain
        # records but keep the first domain to stay tolerant.
        return cls(ip=parts[0], domain=parts[1])

    def to_pihole(self) -> str:
        return f"{self.ip} {self.domain}"


class DnsHostsBackend(Protocol):
    """What `IpAllocator` needs from Pi-hole. `PiholeClient` implements it;
    tests provide an in-memory fake."""

    def list_hosts(self) -> list[DnsHostRecord]: ...

    def add_host(self, record: DnsHostRecord) -> None: ...

    def delete_host(self, record: DnsHostRecord) -> None: ...


class PiholeClient:
    """Context-managed session against a Pi-hole v6 instance.

    Usage::

        with PiholeClient(url, app_password) as pihole:
            pihole.add_host(DnsHostRecord("192.168.1.130", "nsft.nath-server.home"))
    """

    def __init__(
        self,
        base_url: str,
        password: str,
        timeout_s: int = const.PIHOLE_HTTP_TIMEOUT_S,
        opener: urllib.request.OpenerDirector | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._password = password
        self._timeout_s = timeout_s
        self._opener = opener or urllib.request.build_opener()
        self._sid: str | None = None
        self._csrf: str | None = None

    # -- session ---------------------------------------------------------------

    def __enter__(self) -> "PiholeClient":
        self.login()
        return self

    def __exit__(self, *_exc) -> None:
        self.logout()

    def login(self) -> None:
        status, body = self._request(
            "POST", const.PIHOLE_AUTH_PATH, {"password": self._password}, authenticated=False
        )
        session = body.get("session") or {}
        if status != 200 or not session.get("valid"):
            raise PiholeAuthError(
                f"Pi-hole authentication failed (HTTP {status}): {session.get('message', body)}"
            )
        self._sid = session["sid"]
        self._csrf = session.get("csrf")

    def logout(self) -> None:
        if self._sid is None:
            return
        try:
            self._request("DELETE", const.PIHOLE_AUTH_PATH)
        except PiholeError:
            # Session expiry is handled server-side anyway; never mask the
            # real error with a logout failure.
            pass
        finally:
            self._sid = None
            self._csrf = None

    # -- dns.hosts -------------------------------------------------------------

    def list_hosts(self) -> list[DnsHostRecord]:
        status, body = self._request("GET", const.PIHOLE_DNS_HOSTS_PATH)
        self._expect(status, (200,), "list dns.hosts")
        raw_hosts: Iterable[str] = body.get("config", {}).get("dns", {}).get("hosts", [])
        return [DnsHostRecord.parse(raw) for raw in raw_hosts]

    def add_host(self, record: DnsHostRecord) -> None:
        status, body = self._request("PUT", self._host_path(record))
        self._expect(status, (200, 201), f"add {record.to_pihole()!r}", body)

    def delete_host(self, record: DnsHostRecord) -> None:
        status, body = self._request("DELETE", self._host_path(record))
        # 404 means it is already gone: idempotent release.
        self._expect(status, (200, 204, 404), f"delete {record.to_pihole()!r}", body)

    # -- internals -------------------------------------------------------------

    @staticmethod
    def _host_path(record: DnsHostRecord) -> str:
        return f"{const.PIHOLE_DNS_HOSTS_PATH}/{urllib.parse.quote(record.to_pihole(), safe='')}"

    @staticmethod
    def _expect(status: int, allowed: tuple[int, ...], action: str, body: dict | None = None) -> None:
        if status not in allowed:
            detail = body.get("error", body) if body else ""
            raise PiholeError(f"Pi-hole refused to {action} (HTTP {status}): {detail}")

    def _request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        authenticated: bool = True,
    ) -> tuple[int, dict]:
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self._base_url + path, data=data, method=method)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if authenticated:
            if self._sid is None:
                raise PiholeAuthError("Not authenticated: call login() first")
            request.add_header(const.PIHOLE_SID_HEADER, self._sid)
            if self._csrf:
                request.add_header(const.PIHOLE_CSRF_HEADER, self._csrf)
        try:
            with self._opener.open(request, timeout=self._timeout_s) as response:
                return response.status, self._decode(response.read())
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, self._decode(exc.read())
        except urllib.error.URLError as exc:
            raise PiholeError(f"Cannot reach Pi-hole at {self._base_url}: {exc.reason}") from exc

    @staticmethod
    def _decode(raw: bytes) -> dict:
        if not raw:
            return {}
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PiholeError(f"Pi-hole returned non-JSON payload: {raw[:200]!r}") from exc
        return decoded if isinstance(decoded, dict) else {"data": decoded}
