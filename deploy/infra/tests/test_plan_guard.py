import json
import unittest

from ..errors import PlanGuardError
from ..plan_guard import TerraformPlanGuard

VM = "proxmox_virtual_environment_vm.app"


def plan(*changes):
    return json.dumps(
        {
            "format_version": "1.2",
            "resource_changes": [
                {"address": address, "change": {"actions": list(actions)}} for address, actions in changes
            ],
        }
    )


class TerraformPlanGuardTests(unittest.TestCase):
    def setUp(self):
        self.guard = TerraformPlanGuard()

    def test_noop_and_update_pass(self):
        self.guard.check(plan((VM, ["no-op"]), ("terraform_data.generation", ["update"])))

    def test_create_passes(self):
        self.guard.check(plan((VM, ["create"])))

    def test_delete_fails(self):
        with self.assertRaises(PlanGuardError):
            self.guard.check(plan((VM, ["delete"])))

    def test_replace_fails_both_orders(self):
        for actions in (["delete", "create"], ["create", "delete"]):
            with self.assertRaises(PlanGuardError):
                self.guard.check(plan((VM, actions)))

    def test_delete_of_unprotected_resource_passes(self):
        self.guard.check(plan(("terraform_data.generation", ["delete"])))

    def test_violation_message_lists_resource(self):
        with self.assertRaises(PlanGuardError) as ctx:
            self.guard.check(plan((VM, ["delete", "create"])))
        self.assertIn(VM, str(ctx.exception))
        self.assertIn("destroy_prod_vm", str(ctx.exception))

    def test_custom_protected_set(self):
        guard = TerraformPlanGuard(["terraform_data.generation"])
        guard.check(plan((VM, ["delete"])))
        with self.assertRaises(PlanGuardError):
            guard.check(plan(("terraform_data.generation", ["delete"])))

    def test_empty_plan(self):
        self.guard.check(json.dumps({"format_version": "1.2"}))


if __name__ == "__main__":
    unittest.main()
