"""Shared constants.

Import this module on its own. It must not import Flask config, because
``lib/_config.py`` selects a class from these names at import time.
"""

# dev          local docker compose
# integration  disposable CI instance: created, deployed, tested, destroyed
# validation   pre-production: same deployment as prod, no automated tests
# prod         production
CONTEXT_DEV = "dev"
CONTEXT_INTEGRATION = "integration"
CONTEXT_VALIDATION = "validation"
CONTEXT_PROD = "prod"

CONTEXTS: tuple[str, ...] = (
    CONTEXT_DEV,
    CONTEXT_INTEGRATION,
    CONTEXT_VALIDATION,
    CONTEXT_PROD,
)

# Contexts deployed on their own VM (everything but local dev).
DEPLOYED_CONTEXTS: tuple[str, ...] = (
    CONTEXT_INTEGRATION,
    CONTEXT_VALIDATION,
    CONTEXT_PROD,
)

DEFAULT_CONTEXT = CONTEXT_DEV
CONTEXT_ENV_VAR = "NATH_STANDALONE_FLASK_TEMPLATE_CONTEXT"

# Contexts where test output and coverage routes are registered.
TEST_UI_CONTEXTS: tuple[str, ...] = (
    CONTEXT_DEV,
    CONTEXT_INTEGRATION,
)

# Default permissions seeded at bootstrap and in the Alembic data migration.
# The slug (first item) is immutable after insert: Python checks has_permission('admin').
DEFAULT_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("admin", "Full administration access"),
    ("read", "Read access"),
    ("write", "Write access"),
    ("delete", "Delete access"),
)
ADMIN_ROLE_NAME = "admin"
PERMISSION_NAME_PATTERN = r"^[a-z][a-z0-9_]*$"

# API tokens issued from Admin → Users. The raw value is shown once; only the hash is stored.
API_TOKEN_PREFIX = "nst_"
API_TOKEN_BYTES = 32
API_TOKEN_DISPLAY_LENGTH = 12
API_TOKEN_HEADER = "X-API-Token"
