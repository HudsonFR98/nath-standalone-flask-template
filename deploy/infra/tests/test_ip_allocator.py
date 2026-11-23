import unittest

from ..environment import Environment
from ..errors import FixedIpError, NoFreeIpError
from ..ip_allocator import IpAllocator, IpPool
from ..pihole_client import DnsHostRecord
from .fakes import FakePihole, FakeProbe

FQDN = "nsft.nath-server.home"


class IpPoolTests(unittest.TestCase):
    def test_iterates_inclusive_range(self):
        pool = IpPool.from_strings("192.168.1.124", "192.168.1.126")
        self.assertEqual([str(ip) for ip in pool], ["192.168.1.124", "192.168.1.125", "192.168.1.126"])

    def test_rejects_inverted_range(self):
        with self.assertRaises(ValueError):
            IpPool.from_strings("192.168.1.200", "192.168.1.124")

    def test_reserved_ignores_empty_strings(self):
        pool = IpPool.from_strings("192.168.1.124", "192.168.1.126", reserved=["", "192.168.1.125"])
        self.assertEqual({str(ip) for ip in pool.reserved}, {"192.168.1.125"})


class IpAllocatorTests(unittest.TestCase):
    def setUp(self):
        self.pool = IpPool.from_strings("192.168.1.124", "192.168.1.127")

    def test_reuses_existing_record_for_fqdn(self):
        pihole = FakePihole([DnsHostRecord("192.168.1.130", FQDN)])
        allocation = IpAllocator(pihole, self.pool).allocate(FQDN)
        self.assertEqual(allocation.ip, "192.168.1.130")
        self.assertTrue(allocation.reused)
        self.assertEqual(pihole.added, [])

    def test_fqdn_match_is_case_insensitive(self):
        pihole = FakePihole([DnsHostRecord("192.168.1.130", FQDN.upper())])
        allocation = IpAllocator(pihole, self.pool).allocate(FQDN)
        self.assertTrue(allocation.reused)

    def test_picks_first_free_address_and_reserves_it(self):
        pihole = FakePihole([DnsHostRecord("192.168.1.124", "other.nath-server.home")])
        allocation = IpAllocator(pihole, self.pool).allocate(FQDN)
        self.assertEqual(allocation.ip, "192.168.1.125")
        self.assertFalse(allocation.reused)
        self.assertEqual(pihole.added, [DnsHostRecord("192.168.1.125", FQDN)])

    def test_skips_alive_hosts_without_dns_record(self):
        pihole = FakePihole()
        probe = FakeProbe(alive=("192.168.1.124",))
        allocation = IpAllocator(pihole, self.pool, probe).allocate(FQDN)
        self.assertEqual(allocation.ip, "192.168.1.125")

    def test_skips_reserved_addresses(self):
        pool = IpPool.from_strings("192.168.1.124", "192.168.1.127", reserved=["192.168.1.124"])
        allocation = IpAllocator(FakePihole(), pool).allocate(FQDN)
        self.assertEqual(allocation.ip, "192.168.1.125")

    def test_pinned_ip_is_preferred_when_free(self):
        allocation = IpAllocator(FakePihole(), self.pool).allocate(FQDN, pinned_ip="192.168.1.126")
        self.assertEqual(allocation.ip, "192.168.1.126")

    def test_fixed_ip_is_used_outside_the_pool_without_probing(self):
        probe = FakeProbe(alive=("192.168.1.50",))
        pihole = FakePihole()
        allocation = IpAllocator(pihole, self.pool, probe).allocate(FQDN, fixed_ip="192.168.1.50")
        self.assertEqual(allocation.ip, "192.168.1.50")
        self.assertFalse(allocation.reused)
        self.assertEqual(pihole.added, [DnsHostRecord("192.168.1.50", FQDN)])
        self.assertEqual(probe.probed, [])

    def test_fixed_ip_reuses_matching_record(self):
        pihole = FakePihole([DnsHostRecord("192.168.1.50", FQDN)])
        allocation = IpAllocator(pihole, self.pool).allocate(FQDN, fixed_ip="192.168.1.50")
        self.assertTrue(allocation.reused)
        self.assertEqual(pihole.added, [])
        self.assertEqual(pihole.deleted, [])

    def test_fixed_ip_replaces_a_different_record_for_the_same_fqdn(self):
        previous = DnsHostRecord("192.168.1.130", FQDN)
        pihole = FakePihole([previous])
        allocation = IpAllocator(pihole, self.pool).allocate(FQDN, fixed_ip="192.168.1.50")
        self.assertEqual(allocation.ip, "192.168.1.50")
        self.assertEqual(pihole.deleted, [previous])
        self.assertEqual(pihole.added, [DnsHostRecord("192.168.1.50", FQDN)])

    def test_fixed_ip_refuses_an_address_owned_by_another_name(self):
        pihole = FakePihole([DnsHostRecord("192.168.1.50", "other.nath-server.home")])
        with self.assertRaises(FixedIpError):
            IpAllocator(pihole, self.pool).allocate(FQDN, fixed_ip="192.168.1.50")
        self.assertEqual(pihole.added, [])

    def test_pinned_ip_falls_back_to_pool_when_taken(self):
        pihole = FakePihole([DnsHostRecord("192.168.1.126", "busy.nath-server.home")])
        allocation = IpAllocator(pihole, self.pool).allocate(FQDN, pinned_ip="192.168.1.126")
        self.assertEqual(allocation.ip, "192.168.1.124")

    def test_raises_when_pool_exhausted(self):
        records = [DnsHostRecord(str(ip), f"h{i}.lan") for i, ip in enumerate(self.pool)]
        with self.assertRaises(NoFreeIpError):
            IpAllocator(FakePihole(records), self.pool).allocate(FQDN)

    def test_ignores_non_ipv4_records(self):
        pihole = FakePihole([DnsHostRecord("fd00::1", "v6.lan")])
        allocation = IpAllocator(pihole, self.pool).allocate(FQDN)
        self.assertEqual(allocation.ip, "192.168.1.124")

    def test_release_removes_record(self):
        record = DnsHostRecord("192.168.1.130", FQDN)
        pihole = FakePihole([record])
        removed = IpAllocator(pihole, self.pool).release(FQDN)
        self.assertEqual(removed, record)
        self.assertEqual(pihole.records, [])

    def test_release_is_noop_when_absent(self):
        pihole = FakePihole()
        self.assertIsNone(IpAllocator(pihole, self.pool).release(FQDN))
        self.assertEqual(pihole.deleted, [])

    def test_dotenv_output_defaults_to_prod_prefix(self):
        allocation = IpAllocator(FakePihole(), self.pool).allocate(FQDN)
        self.assertEqual(
            allocation.to_dotenv(),
            "PROD_VM_IP=192.168.1.124\nPROD_VM_FQDN=nsft.nath-server.home\nPROD_VM_IP_REUSED=false\n",
        )

    def test_dotenv_output_is_prefixed_by_environment(self):
        fqdn = "nsft.integration.nath-server.home"
        allocation = IpAllocator(FakePihole(), self.pool).allocate(fqdn)
        self.assertEqual(
            allocation.to_dotenv(Environment("integration")),
            f"INTEGRATION_VM_IP=192.168.1.124\nINTEGRATION_VM_FQDN={fqdn}\nINTEGRATION_VM_IP_REUSED=false\n",
        )


if __name__ == "__main__":
    unittest.main()
