# Dockerfile for nath_standalone_flask_template
ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV NATH_STANDALONE_FLASK_TEMPLATE_CONTEXT=dev
ENV DB_IP=db

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libldap2-dev \
    libpq-dev \
    libsasl2-dev \
    postgresql-client \
    libjpeg-dev \
    libfreetype6-dev \
    zlib1g-dev \
    nano \
    git \
    build-essential \
    wget \
    gnupg \
    gcc \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create app user with specific UID/GID to match host
RUN groupadd -g 1000 web && useradd -r -g web -u 1000 -m -s /bin/bash web

# Create necessary directories with correct permissions
RUN mkdir -p /var/log/nath_standalone_flask_template /opt/nath_standalone_flask_template_docs /var/backup \
    && chown -R web:web /var/log/nath_standalone_flask_template /opt/nath_standalone_flask_template_docs /var/backup \
    && chmod 775 /var/log/nath_standalone_flask_template /var/backup \
    && touch /var/log/nath_standalone_flask_template/nath_standalone_flask_template.log \
    && chown web:web /var/log/nath_standalone_flask_template/nath_standalone_flask_template.log \
    && chmod 664 /var/log/nath_standalone_flask_template/nath_standalone_flask_template.log

# Set working directory
WORKDIR /opt/nath_standalone_flask_template

# Copy application code
COPY --chown=web:web . /opt/nath_standalone_flask_template/

# Create and activate virtual environment
RUN python -m venv /opt/env3/nath_standalone_flask_template \
    && chown -R web:web /opt/env3/nath_standalone_flask_template

# Install Python dependencies
RUN /opt/env3/nath_standalone_flask_template/bin/pip install --upgrade pip setuptools \
    && /opt/env3/nath_standalone_flask_template/bin/pip install -r deploy/requirements.txt \
    && /opt/env3/nath_standalone_flask_template/bin/pip install -e .

ENV PATH="/opt/env3/nath_standalone_flask_template/bin:${PATH}"

# Expose port
EXPOSE 8080

# Set up entrypoint
COPY deploy/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh && chown web:web /docker-entrypoint.sh

# Switch to web user for the rest of the operations
USER web

ENTRYPOINT ["/docker-entrypoint.sh"]
