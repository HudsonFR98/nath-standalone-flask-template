"""Decide the generation number of an environment's VM from Terraform state.

Rules (see docs/infra_automation/02_terraform_proxmox.md):

* VM resource and counter both in state  -> keep the stored generation.
* Counter in state but VM resource gone  -> stored generation + 1.
* Empty / fresh state                     -> seed (``<ENV>_VM_GENERATION_SEED``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from . import const


@dataclass(frozen=True)
class StateSnapshot:
    """The two facts we need from ``terraform show -json``."""

    vm_present: bool
    stored_generation: int | None

    @classmethod
    def from_show_json(
        cls,
        payload: str | dict[str, Any],
        vm_address: str = const.TERRAFORM_VM_RESOURCE_ADDRESS,
        generation_address: str = const.TERRAFORM_GENERATION_RESOURCE_ADDRESS,
    ) -> "StateSnapshot":
        data = json.loads(payload) if isinstance(payload, str) else payload
        resources = cls._root_resources(data)

        vm_present = any(r.get("address") == vm_address for r in resources)
        stored: int | None = None
        for resource in resources:
            if resource.get("address") == generation_address:
                values = resource.get("values") or {}
                raw = values.get("output", values.get("input"))
                if raw is not None:
                    stored = int(raw)
                break
        return cls(vm_present=vm_present, stored_generation=stored)

    @staticmethod
    def _root_resources(data: dict[str, Any]) -> list[dict[str, Any]]:
        # `terraform show -json` on an empty state returns {"format_version": "..."}.
        return (data.get("values") or {}).get("root_module", {}).get("resources", []) or []


class GenerationResolver:
    def __init__(self, seed: int = const.GENERATION_DEFAULT_SEED) -> None:
        if seed < 1:
            raise ValueError("generation seed must be >= 1")
        self._seed = seed

    def resolve(self, snapshot: StateSnapshot) -> int:
        if snapshot.stored_generation is None:
            return self._seed
        if snapshot.vm_present:
            return snapshot.stored_generation
        return snapshot.stored_generation + 1
