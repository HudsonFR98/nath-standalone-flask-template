#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
until pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do
    echo "Waiting for PostgreSQL to be ready..."
    sleep 2
done

# Check if the application database exists
DB_EXISTS=$(psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -tAc "SELECT 1 FROM pg_database WHERE datname = '${NSFT_DB_NAME}'")

# Create the application database if it doesn't exist
if [ -z "$DB_EXISTS" ]; then
    echo "Creating database ${NSFT_DB_NAME}..."
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "CREATE DATABASE ${NSFT_DB_NAME};"
    echo "Waiting for database to be fully initialized..."
    sleep 5
else
    echo "Database ${NSFT_DB_NAME} already exists."
fi


echo "Database initialization completed successfully."
