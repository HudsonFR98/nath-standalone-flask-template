import os
import logging
import tempfile

from logging.config import dictConfig

from .const import (
    CONTEXT_DEV,
    CONTEXT_ENV_VAR,
    CONTEXT_INTEGRATION,
    CONTEXT_PROD,
    CONTEXT_VALIDATION,
)

"""
Configuration module for nath_standalone_flask_template application.

Deployment Architecture:
- DEV: Uses external database specified by DB_IP environment variable
- INTEGRATION/VALIDATION/PROD: Use Docker containers with local PostgreSQL databases
  - Database container name: 'nsft_db_{context}' (e.g., 'nsft_db_integration', 'nsft_db_validation', 'nsft_db_prod')
  - Database name: 'nsft'
  - All environments accessible on port 8080
  - Deploy vs Update operations supported (data preservation during updates)

Environment Variables:
- NATH_STANDALONE_FLASK_TEMPLATE_CONTEXT: Required for all environments (dev, integration, validation, prod)
- DB_IP: Required for every environment (container name on deployed hosts, host address in dev)

Session Security:
- All environments currently configured for HTTP (SESSION_COOKIE_SECURE = False)
- When HTTPS is enabled, update SESSION_COOKIE_SECURE to True in respective configs
- SESSION_COOKIE_SAMESITE set to 'Lax' for HTTP compatibility
"""


def setup_logging():
    """Set up logging configuration with proper error handling."""
    log_dir = '/var/log/nath_standalone_flask_template'
    log_file = os.path.join(log_dir, 'nath_standalone_flask_template.log')
    
    # Ensure log directory exists and is writable
    try:
        os.makedirs(log_dir, exist_ok=True)
        # Test if we can write to the directory
        test_file = os.path.join(log_dir, '.test_write')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        use_file_handler = True
    except (OSError, PermissionError):
        # If we can't write to the log directory, use a temporary file or console only
        use_file_handler = False
        log_file = os.path.join(tempfile.gettempdir(), 'nath_standalone_flask_template.log')
    
    config = {
        'version': 1,
        'formatters': {'default': {
            'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        }},
        'handlers': {
            'console': {
                'level': 'DEBUG',
                'formatter': 'default',
                'class': 'logging.StreamHandler',
            },
        },
        'loggers': {
            'nath_standalone_flask_template': {
                'handlers': ['console'],
                'level': 'DEBUG',
                'propagate': False
            },
            'sqlalchemy.engine': {
                'handlers': ['console'],
                'level': 'WARNING',
                'propagate': False
            },
        }
    }
    
    # Add file handler only if we can write to the log directory
    if use_file_handler:
        config['handlers']['file'] = {
            'level': 'DEBUG',
            'formatter': 'default',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': log_file,
            'mode': 'a',
            'maxBytes': 5000000,
            'backupCount': 10,
        }
        config['loggers']['nath_standalone_flask_template']['handlers'].append('file')
        config['loggers']['sqlalchemy.engine']['handlers'].append('file')
    
    try:
        dictConfig(config)
    except Exception as e:
        # Fallback to basic logging if configuration fails
        logging.basicConfig(
            level=logging.DEBUG,
            format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
        )
        logging.warning(f"Failed to configure logging: {e}")


# Set up logging when module is imported
setup_logging()

def require_env(name: str) -> str:
    """
    Return required env var value
    Raises a clear error if missing/empty.
    """
    value = os.environ.get(name)
    if value is None or str(value).strip() == "":
        raise RuntimeError(f"La variable d'environnement {name} n'est pas renseignée")
    return value


def optional_env(name: str) -> str | None:
    """Return env var value, or None if unset or blank."""
    value = os.environ.get(name)
    if value is None or str(value).strip() == "":
        return None
    return value


def reviewer_bootstrap_configured() -> bool:
    """True when REVIEWER_USER_USERNAME and REVIEWER_USER_PASSWORD are both set."""
    return bool(optional_env("REVIEWER_USER_USERNAME") and optional_env("REVIEWER_USER_PASSWORD"))


def build_db_uri() -> str:
    """
    Build SQLAlchemy DB URI from environment variables
    Required:
      - DB_IP
      - POSTGRES_USER
      - POSTGRES_PASSWORD
      - NSFT_DB_NAME
    """
    host = require_env("DB_IP")
    user = require_env("POSTGRES_USER")
    password = require_env("POSTGRES_PASSWORD")
    db_name = require_env("NSFT_DB_NAME")
    return f"postgresql://{user}:{password}@{host}/{db_name}"


class Config(object):
    """
    Base configuration class.
    
    Session configurations are overridden by environment-specific classes:
    - DEV: Relaxed settings for debugging (HTTP, JavaScript access)
    - INTEGRATION/VALIDATION/PROD: Standard security settings (HTTP, no JavaScript access)
    - All environments currently configured for HTTP compatibility
    - When HTTPS is enabled, update SESSION_COOKIE_SECURE to True
    """

    EMAIL_DEV = 'natha.debanne@gmail.com'
    SETTINGS = None
    STATIC_URI = '/static'
    SECRET_KEY = require_env("SECRET_KEY")

    # Telegram notification settings
    TELEGRAM_BOT_TOKEN = require_env("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = require_env("TELEGRAM_CHAT_ID")

    # Initial admin bootstrap user (used only if no users exist yet)
    ADMIN_USER_USERNAME = require_env("ADMIN_USER_USERNAME")
    ADMIN_USER_PASSWORD = require_env("ADMIN_USER_PASSWORD")
    ADMIN_USER_FIRST_NAME = require_env("ADMIN_USER_FIRST_NAME")
    ADMIN_USER_LAST_NAME = require_env("ADMIN_USER_LAST_NAME")
    ADMIN_USER_EMAIL = require_env("ADMIN_USER_EMAIL")

    REVIEWER_USER_USERNAME = optional_env("REVIEWER_USER_USERNAME")
    REVIEWER_USER_PASSWORD = optional_env("REVIEWER_USER_PASSWORD")
    REVIEWER_USER_FIRST_NAME = optional_env("REVIEWER_USER_FIRST_NAME")
    REVIEWER_USER_LAST_NAME = optional_env("REVIEWER_USER_LAST_NAME")
    REVIEWER_USER_EMAIL = optional_env("REVIEWER_USER_EMAIL")

    # Database (same building blocks in all contexts; DB host differs via DB_IP)
    DB_URI = build_db_uri()
    SQLALCHEMY_DATABASE_URI = DB_URI
    APP_NAME = "Nath Standalone Flask Template"



    # (Legacy) Email settings kept for backward compatibility, no longer used for errors
    ERROR_EMAIL_FROM = ''
    ERROR_EMAIL_TO = EMAIL_DEV
    ERROR_EMAIL_SMTP_SERVER = ''
    ERROR_EMAIL_SMTP_USER = ''
    ERROR_EMAIL_SMTP_PASSWORD = ''
    ERROR_EMAIL_SMTP_PORT = 587  # Standard SMTP port, adjust if needed

    # Session configuration (base settings, overridden by environment classes)
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Babel configuration for internationalization
    BABEL_DEFAULT_LOCALE = 'en'
    BABEL_DEFAULT_TIMEZONE = 'UTC'
    BABEL_TRANSLATION_DIRECTORIES = 'translations'
    LANGUAGES = {
        'en': 'English',
        'fr': 'Français'
    }

    # docs paths
    DOC_DIR = '/opt/nath_standalone_flask_template_docs'

    # Base URL for task execution (used by test_simple_route task)
    BASE_URL = 'http://localhost:8080'


class ProdConfig(Config):

    CONTEXT = 'prod'
    LOG_LEVEL = logging.ERROR
    
    # Session settings for production (HTTP environment)
    SESSION_COOKIE_SECURE = False  # Disabled for HTTP
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'  # Changed from 'Strict' to 'Lax' for better compatibility


class DevConfig(Config):

    CONTEXT = 'dev'
    DEBUG = True
    TESTING = False
    LOG_LEVEL = logging.DEBUG
    PRESERVE_CONTEXT_ON_EXCEPTION = False  # Helps with better error reporting
    
    # Enable Flask's debug toolbar
    DEBUG_TB_ENABLED = True
    DEBUG_TB_INTERCEPT_REDIRECTS = False
    
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = False  # Allow JavaScript access for debugging
    SESSION_COOKIE_SAMESITE = 'Lax'


class ValidationConfig(Config):

    CONTEXT = 'validation'
    LOG_LEVEL = logging.ERROR

    # Session settings for validation (HTTP environment)
    SESSION_COOKIE_SECURE = False  # Disabled for HTTP
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'


class IntegrationConfig(Config):

    CONTEXT = 'integration'
    TESTING = True
    LOG_LEVEL = logging.ERROR
    SERVER_NAME = 'localhost'

    # Session settings for integration (HTTP environment)
    SESSION_COOKIE_SECURE = False  # Disabled for HTTP
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'


require_env(CONTEXT_ENV_VAR)
require_env("DB_IP")


_envs = {
    CONTEXT_INTEGRATION: IntegrationConfig,
    CONTEXT_DEV: DevConfig,
    CONTEXT_VALIDATION: ValidationConfig,
    CONTEXT_PROD: ProdConfig,
}
config = _envs[os.environ[CONTEXT_ENV_VAR]]
