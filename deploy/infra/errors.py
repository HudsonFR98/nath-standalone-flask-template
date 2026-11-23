"""Exception hierarchy for the infra helpers."""


class InfraError(Exception):
    """Base class for every error raised by `deploy.infra`."""


class PiholeError(InfraError):
    """Pi-hole API returned an unexpected status or payload."""


class PiholeAuthError(PiholeError):
    """Authentication against Pi-hole failed."""


class NoFreeIpError(InfraError):
    """The pool has no address left that is neither reserved nor alive."""


class FixedIpError(InfraError):
    """A caller-chosen address cannot be assigned to this FQDN."""


class PlanGuardError(InfraError):
    """The Terraform plan contains destructive actions on a protected resource."""


class SshTimeoutError(InfraError):
    """The host did not expose SSH before the deadline."""
