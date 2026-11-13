class RestException(Exception):
    pass


class DomainError(Exception):
    """Expected business-rule failure (unique name, system permission, ...)."""
