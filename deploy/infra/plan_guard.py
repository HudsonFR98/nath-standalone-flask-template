"""Refuse Terraform plans that would delete or replace protected resources.

Works on the output of ``terraform show -json tfplan``. Used by the CI apply
job so that a drift (e.g. someone changed the template VMID) never turns into
an automatic destruction of the prod VM. Manual destruction goes through the
dedicated ``destroy_prod_vm`` job, which does not run the guard.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from . import const
from .errors import PlanGuardError


@dataclass(frozen=True)
class PlanViolation:
    address: str
    actions: tuple[str, ...]

    def __str__(self) -> str:
        return f"{self.address}: {' + '.join(self.actions)}"


class TerraformPlanGuard:
    def __init__(self, protected_addresses: Iterable[str] = (const.TERRAFORM_VM_RESOURCE_ADDRESS,)) -> None:
        self._protected = frozenset(protected_addresses)

    def violations(self, plan: str | dict[str, Any]) -> list[PlanViolation]:
        data = json.loads(plan) if isinstance(plan, str) else plan
        found: list[PlanViolation] = []
        for change in data.get("resource_changes", []) or []:
            address = change.get("address")
            if address not in self._protected:
                continue
            actions = tuple(change.get("change", {}).get("actions", []))
            if self._is_destructive(actions):
                found.append(PlanViolation(address=address, actions=actions))
        return found

    def check(self, plan: str | dict[str, Any]) -> None:
        found = self.violations(plan)
        if found:
            details = "\n".join(f"  - {v}" for v in found)
            raise PlanGuardError(
                "Refusing to apply: the plan destroys or replaces protected resources.\n"
                f"{details}\n"
                "Use the manual destroy_prod_vm job if this is intended."
            )

    @staticmethod
    def _is_destructive(actions: tuple[str, ...]) -> bool:
        if const.TERRAFORM_ACTION_DELETE in actions:
            return True
        return set(actions) in const.TERRAFORM_REPLACE_ACTIONS
