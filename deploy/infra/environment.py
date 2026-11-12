"""Deployment environment (integration / validation / prod) naming helpers.

The CI pipeline runs the same infra jobs for every environment; what differs
is the name, and everything derived from it: the GitLab Terraform state, the
dotenv variable prefix and the VM name suffix.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import const


@dataclass(frozen=True)
class Environment:
    """A deployment environment identified by its lower-case name."""

    name: str

    def __post_init__(self) -> None:
        if not re.match(const.ENVIRONMENT_NAME_PATTERN, self.name):
            raise ValueError(
                f"invalid environment name {self.name!r}: expected {const.ENVIRONMENT_NAME_PATTERN}"
            )

    @classmethod
    def default(cls) -> "Environment":
        return cls(const.DEFAULT_ENVIRONMENT)

    @property
    def is_known(self) -> bool:
        """True for the environments the project deploys (not for ad-hoc names)."""
        return self.name in const.ENVIRONMENTS

    @property
    def dotenv_prefix(self) -> str:
        """``prod`` -> ``PROD``; ``my-env`` -> ``MY_ENV`` (shell-safe)."""
        return self.name.upper().replace("-", "_")

    @property
    def state_name(self) -> str:
        """GitLab-managed Terraform state name (``<env>-vm``)."""
        return f"{self.name}-vm"

    def dotenv_key(self, suffix: str) -> str:
        return f"{self.dotenv_prefix}_{suffix}"

    @property
    def vm_ip_key(self) -> str:
        return self.dotenv_key(const.DOTENV_SUFFIX_VM_IP)

    @property
    def fqdn_key(self) -> str:
        return self.dotenv_key(const.DOTENV_SUFFIX_FQDN)

    @property
    def ip_reused_key(self) -> str:
        return self.dotenv_key(const.DOTENV_SUFFIX_IP_REUSED)

    @property
    def generation_key(self) -> str:
        return self.dotenv_key(const.DOTENV_SUFFIX_GENERATION)

    def __str__(self) -> str:
        return self.name
