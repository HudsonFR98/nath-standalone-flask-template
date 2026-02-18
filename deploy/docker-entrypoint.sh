#!/bin/bash
set -e

require_env() {
    local name="$1"
    if [ -z "${!name:-}" ]; then
        echo "Error: missing required environment variable: ${name}" >&2
        exit 1
    fi
}

# Function to run as web user (only if we're not already web user)
run_as_web() {
    if [ "$(id -u)" = "1000" ]; then
        # We're already running as web user
        eval "$1"
    else
        # Switch to web user
        su - web -c "$1"
    fi
}

require_env "NATH_STANDALONE_FLASK_TEMPLATE_CONTEXT"
require_env "DB_IP"
require_env "POSTGRES_USER"
require_env "POSTGRES_PASSWORD"
require_env "NSFT_DB_NAME"

DB_HOST="${DB_IP}"
DB_USER="${POSTGRES_USER}"
DB_PASSWORD="${POSTGRES_PASSWORD}"
DB_NAME="${NSFT_DB_NAME}"


# Wait for the nsft database to be ready
echo "Waiting for database ${DB_NAME} to be ready on ${DB_HOST}..."
max_retries=30
retries=0
while [ $retries -lt $max_retries ]; do
    if PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -U "${DB_USER}" -d "${DB_NAME}" -c "SELECT 1" > /dev/null 2>&1; then
        echo "Database ${DB_NAME} is ready!"
        break
    fi
    retries=$((retries+1))
    echo "Database ${DB_NAME} not ready yet, retrying... ($retries/$max_retries)"
    sleep 2
done

if [ $retries -eq $max_retries ]; then
    echo "Error: Maximum retries reached. Database ${DB_NAME} is not available on ${DB_HOST}."
    exit 1
fi

# Install requirements and run database migrations
echo "Setting up application..."
run_as_web "cd /opt/nath_standalone_flask_template && \
    NATH_STANDALONE_FLASK_TEMPLATE_CONTEXT=$NATH_STANDALONE_FLASK_TEMPLATE_CONTEXT \
    DB_IP=${DB_HOST} \
    /opt/env3/nath_standalone_flask_template/bin/pip install -r deploy/requirements.txt && \
    /opt/env3/nath_standalone_flask_template/bin/alembic upgrade head"


# Determine which server to use based on context
if [ "$NATH_STANDALONE_FLASK_TEMPLATE_CONTEXT" = "dev" ]; then
    echo "Starting Flask development server with hot reloading..."
    # Use Flask development server for hot reloading in dev mode
    exec /opt/env3/nath_standalone_flask_template/bin/python nath_standalone_flask_template_app.py
else
    echo "Starting Gunicorn production server..."
    # Use Gunicorn for production/demo/test modes
    exec /opt/env3/nath_standalone_flask_template/bin/gunicorn --bind 0.0.0.0:8080 --log-level=debug --capture-output --enable-stdio-inheritance nath_standalone_flask_template_app:app
fi
