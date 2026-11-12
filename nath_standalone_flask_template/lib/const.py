"""Deployment context names.

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
