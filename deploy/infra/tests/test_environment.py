import unittest

from .. import const
from ..environment import Environment


class EnvironmentTests(unittest.TestCase):
    def test_default_is_prod(self):
        self.assertEqual(Environment.default().name, "prod")

    def test_known_environments(self):
        for name in ("integration", "validation", "prod"):
            self.assertTrue(Environment(name).is_known, name)
        self.assertFalse(Environment("sandbox").is_known)
        self.assertEqual(set(const.ENVIRONMENTS), {"integration", "validation", "prod"})

    def test_dotenv_keys_are_prefixed_with_upper_name(self):
        env = Environment("integration")
        self.assertEqual(env.vm_ip_key, "INTEGRATION_VM_IP")
        self.assertEqual(env.fqdn_key, "INTEGRATION_VM_FQDN")
        self.assertEqual(env.ip_reused_key, "INTEGRATION_VM_IP_REUSED")
        self.assertEqual(env.generation_key, "INTEGRATION_VM_GENERATION")

    def test_prod_keys_keep_historical_names(self):
        env = Environment("prod")
        self.assertEqual(env.vm_ip_key, "PROD_VM_IP")
        self.assertEqual(env.generation_key, "PROD_VM_GENERATION")

    def test_state_name(self):
        self.assertEqual(Environment("validation").state_name, "validation-vm")

    def test_hyphen_becomes_underscore_in_prefix(self):
        self.assertEqual(Environment("prod-sandbox").dotenv_prefix, "PROD_SANDBOX")

    def test_rejects_invalid_names(self):
        for bad in ("", "Prod", "prod vm", "1prod", "prod_vm"):
            with self.assertRaises(ValueError, msg=bad):
                Environment(bad)

    def test_str(self):
        self.assertEqual(str(Environment("prod")), "prod")


if __name__ == "__main__":
    unittest.main()
