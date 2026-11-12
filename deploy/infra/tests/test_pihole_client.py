import io
import json
import unittest
import urllib.error

from .. import const
from ..errors import PiholeAuthError, PiholeError
from ..pihole_client import DnsHostRecord, PiholeClient


class FakeResponse(io.BytesIO):
    def __init__(self, status, payload):
        super().__init__(json.dumps(payload).encode() if payload is not None else b"")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class FakeOpener:
    """Records requests and replays scripted (status, payload) answers."""

    def __init__(self, answers):
        self._answers = list(answers)
        self.requests = []

    def open(self, request, timeout=None):  # noqa: ARG002
        self.requests.append(request)
        status, payload = self._answers.pop(0)
        if status >= 400:
            raise urllib.error.HTTPError(
                request.full_url, status, "err", {}, FakeResponse(status, payload)
            )
        return FakeResponse(status, payload)


LOGIN_OK = (200, {"session": {"valid": True, "sid": "sid123", "csrf": "csrf456"}})
LOGOUT_OK = (204, None)


class DnsHostRecordTests(unittest.TestCase):
    def test_parse_and_format(self):
        record = DnsHostRecord.parse("192.168.1.130 nsft.nath-server.home extra.alias")
        self.assertEqual(record, DnsHostRecord("192.168.1.130", "nsft.nath-server.home"))
        self.assertEqual(record.to_pihole(), "192.168.1.130 nsft.nath-server.home")

    def test_parse_rejects_garbage(self):
        with self.assertRaises(PiholeError):
            DnsHostRecord.parse("garbage")


class PiholeClientTests(unittest.TestCase):
    def test_login_sets_headers_and_logout_closes_session(self):
        opener = FakeOpener([LOGIN_OK, (200, {"config": {"dns": {"hosts": ["192.168.1.1 gw.lan"]}}}), LOGOUT_OK])
        with PiholeClient("http://pihole/", "secret", opener=opener) as client:
            hosts = client.list_hosts()

        self.assertEqual(hosts, [DnsHostRecord("192.168.1.1", "gw.lan")])
        login, listing, logout = opener.requests
        self.assertEqual(login.full_url, "http://pihole" + const.PIHOLE_AUTH_PATH)
        self.assertEqual(json.loads(login.data), {"password": "secret"})
        # urllib capitalises header names as "X-ftl-sid".
        self.assertEqual(listing.get_header(const.PIHOLE_SID_HEADER.capitalize()), "sid123")
        self.assertEqual(listing.get_header(const.PIHOLE_CSRF_HEADER.capitalize()), "csrf456")
        self.assertEqual(logout.get_method(), "DELETE")

    def test_login_failure_raises(self):
        opener = FakeOpener([(401, {"session": {"valid": False, "message": "password incorrect"}})])
        with self.assertRaises(PiholeAuthError):
            PiholeClient("http://pihole", "bad", opener=opener).login()

    def test_add_host_url_encodes_record(self):
        opener = FakeOpener([LOGIN_OK, (201, {}), LOGOUT_OK])
        with PiholeClient("http://pihole", "s", opener=opener) as client:
            client.add_host(DnsHostRecord("192.168.1.130", "nsft.nath-server.home"))
        put = opener.requests[1]
        self.assertEqual(put.get_method(), "PUT")
        self.assertTrue(put.full_url.endswith("/api/config/dns/hosts/192.168.1.130%20nsft.nath-server.home"))

    def test_add_host_error_raises(self):
        opener = FakeOpener([LOGIN_OK, (400, {"error": {"message": "bad"}}), LOGOUT_OK])
        with self.assertRaises(PiholeError):
            with PiholeClient("http://pihole", "s", opener=opener) as client:
                client.add_host(DnsHostRecord("192.168.1.130", "x.lan"))

    def test_delete_host_tolerates_404(self):
        opener = FakeOpener([LOGIN_OK, (404, {"error": "not found"}), LOGOUT_OK])
        with PiholeClient("http://pihole", "s", opener=opener) as client:
            client.delete_host(DnsHostRecord("192.168.1.130", "x.lan"))

    def test_unauthenticated_call_refused(self):
        with self.assertRaises(PiholeAuthError):
            PiholeClient("http://pihole", "s", opener=FakeOpener([])).list_hosts()


if __name__ == "__main__":
    unittest.main()
