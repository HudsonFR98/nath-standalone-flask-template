NATH_STANDALONE_FLASK_TEMPLATE
============================


# Technical documentation for the Nath Standalone Flask Template Application

The application's CI/CD pipeline is organized through GitLab CI/CD, with distinct stages for different environments. Here's a step-by-step breakdown of how it works:

## Development Setup

### Prerequisites
- Docker and Docker Compose installed
- Git

### Renaming the Application (For New Projects)

If you're starting a new project based on this template, you'll want to rename the application to reflect your project's name. Use the provided rename script:

```bash
./rename_app.sh
```

The script will prompt you for:
- **Old names**: The current template names (e.g., `nsft`, `nath-standalone-flask-template`)
- **New names**: Your desired project names (e.g., `myapp`, `my-awesome-application`)

The script automatically handles all name variations:
- Short name: `nsft` → `myapp`
- Full name with hyphens: `nath-standalone-flask-template` → `my-awesome-application`
- Full name with underscores: `nath_standalone_flask_template` → `my_awesome_application`
- Full name in uppercase: `NATH_STANDALONE_FLASK_TEMPLATE` → `MY_AWESOME_APPLICATION`
- Full name in title case: `Nath Standalone Flask Template` → `My Awesome Application`

**Important:** Run this script before making any other changes to the project, as it will rename the entire application structure.

### Quick Start
1. Clone the repository
2. Run the setup script:
   ```bash
   ./setup_dev.sh
   ```
3. Start by building the development environment:
   ```bash
   docker compose up --build
   ```
   If the app is already built, you can simply use:
   ```bash
      docker compose up
   ```
4. Access the application at http://localhost:8080


### Development Environment Details
- **Database**: PostgreSQL 15 on port 5433 (container: `nsft_db_dev`)
- **Application**: Flask app on port 8080 (container: `nsft_app_dev`)
- **Redis**: Redis on port 6380 (container: `nsft_redis_dev`)
- **Network**: `nsft_network_dev`
- **Logs**: Stored in `./logs/` directory
- **User**: Container runs as UID 1000 for proper file permissions


**Environment variables**:
   - Set in docker-compose.yml for local development
   - Can be overridden with a .env file

**Compatibility Notes**:
   - The docker-compose.yml file uses version 3.8 for compatibility with Docker Compose 2.35.1 and Docker 28.1.1
   - The CI/CD pipeline uses Docker 28.1.1 for building and testing
   - The PostgreSQL container uses the Alpine-based image for better compatibility
   - Both containers have healthchecks configured to ensure proper initialization
   - Volume configurations have been simplified for better compatibility
   - The Ansible deployment scripts install the full set of Docker packages needed for Docker 28.1.1

**Run test in development**
   ```
   docker exec -it nsft_app_dev bash -c "NATH_STANDALONE_FLASK_TEMPLATE_CONTEXT=dev DB_IP=nsft_db_dev /opt/env3/nath_standalone_flask_template/bin/python nath_standalone_flask_template/tests/run_tests.py"
   ```

### Resetting Development Database or Changing Database Password
If you need to reset all development data (for example, after changing the database password or to start with a clean database):

1. **Stop and remove all containers and volumes:**
   ```bash
   docker compose down -v --remove-orphans
   ```
   This will delete all data in your development database. **Make sure to back up any important data first!**

2. **Rebuild and start the containers:**
   ```bash
   docker compose up --build
   ```
   This will recreate the database with the new password and initialize it with the default data.

**Note:**
- The database password is set in `docker-compose.yml` under the `POSTGRES_PASSWORD` environment variable for the `db` service.
- The application and all configuration files must use the same password as set in the database container.
- If you change the password, update it everywhere (see `docker-compose.yml`, `.gitlab-ci.yml`, `nath_standalone_flask_template/lib/_config.py`, and deployment scripts).

### Restoring Database from Backup
If you need to restore your development database from a backup file in the `backups` directory:

1. **Stop your application container to prevent data corruption:**
   ```bash
   docker compose stop app
   ```

2. **Stop and remove the database container:**
   ```bash
   docker compose stop db
   docker compose rm -f db
   ```

3. **Remove the database volume to ensure a clean restore:**
   ```bash
   docker volume rm nath-standalone-flask-template_postgres_data
   ```

4. **Start the database container fresh:**
   ```bash
   docker compose up -d db
   ```

5. **Wait for the database to be ready (check health status):**
   ```bash
   docker compose ps db
   ```

6. **Restore from your chosen backup file. For example, to restore from the most recent backup:**
   ```bash
   docker exec -i nsft_db_dev psql -U web -d nsft < backups/nsft_backup_YYYYMMDD_HHMMSS.sql
   ```

   Or if you want to restore to the `postgres` database (which is the default):
   ```bash
   docker exec -i nsft_db_dev psql -U web -d postgres < backups/nsft_backup_YYYYMMDD_HHMMSS.sql
   ```

7. **Start your application container:**
   ```bash
   docker compose up -d app
   ```


## Testing

Pytest lives in `nath_standalone_flask_template/tests/`. The suite talks to Postgres, so a full run needs a database (local Compose with `NATH_STANDALONE_FLASK_TEMPLATE_CONTEXT=dev`, or the integration VM).

Context-only checks do not open the database (`NO_DB` in `test_context.py`):

```bash
NATH_STANDALONE_FLASK_TEMPLATE_CONTEXT=integration \
DB_IP=127.0.0.1 \
POSTGRES_USER=web POSTGRES_PASSWORD=web POSTGRES_DB=postgres NSFT_DB_NAME=nsft \
SECRET_KEY=dev TELEGRAM_BOT_TOKEN=t TELEGRAM_CHAT_ID=1 \
ADMIN_USER_USERNAME=admin ADMIN_USER_PASSWORD=admin \
ADMIN_USER_FIRST_NAME=A ADMIN_USER_LAST_NAME=B ADMIN_USER_EMAIL=a@b.c \
python3 -m pytest nath_standalone_flask_template/tests/test_context.py -q
```

Infra helpers (Pi-hole, IP pool, Terraform plan guard) are stdlib unit tests:

```bash
cd deploy && python3 -m unittest discover -s infra/tests -t .
```

On a deployed integration VM, CI runs the same app suite inside the container via `deploy/ansible/run_tests.yml`.

## GitLab CI/CD

`.gitlab-ci.yml` stages, in order: `docker`, `integration`, `validation`, `prod`.

1. **docker** — build and push the app image (`build_docker`) on every branch and merge request.
2. **integration** — allocate a Pi-hole IP, create the VM with Terraform, deploy with Ansible, run pytest in the container, then destroy the VM. `INTEGRATION_KEEP_VM=true` makes that destroy manual.
3. **validation** — same VM flow after integration tests pass. No automated tests. `destroy_validation_vm` is manual.
4. **prod** — `master` only. VM setup runs on the chain; `update_prod` and `destroy_prod_vm` are manual.

`dev` stays on local Docker Compose and is not a CI environment.

A branch that already has an open merge request runs the merge-request pipeline only.

## Environments

`NATH_STANDALONE_FLASK_TEMPLATE_CONTEXT` selects the class in `nath_standalone_flask_template/lib/_config.py`. Names live in `nath_standalone_flask_template/lib/const.py`.

| Context | Role |
|---|---|
| `dev` | Local Compose. `DevConfig`. |
| `integration` | Disposable CI VM `nsft.integration.nath-server.home`. `IntegrationConfig` (`TESTING = True`). |
| `validation` | Pre-production VM `nsft.validation.nath-server.home`. `ValidationConfig`. |
| `prod` | `nsft.nath-server.home`. `ProdConfig`. HTTP on port 80 on the VM. |

Deployed hosts are created by Terraform (`deploy/terraform/<env>`) and registered in Pi-hole before Ansible runs. See `docs/infra_automation/`.

`DB_IP` is required in every context: the database container name on a VM, or the Compose service host in dev.

## Deployment

GitLab calls `python3 deploy/ansible_deploy.py`.

- `--action deploy` or `update` runs `deploy/ansible/docker_deploy.yml` (Docker, directories, registry CA, files, containers, HTTP check).
- `--action test` runs `deploy/ansible/run_tests.yml` inside `nsft_app_<env>`.
- `--env` is `integration`, `validation`, or `prod`.
- Ansible connects as `Nath` (cloud-init user on the template VM).

An update keeps the Postgres volume. A fresh `deploy` recreates containers.

CI variables are listed at the top of `.gitlab-ci.yml`. Shared Proxmox/Pi-hole variables and all `INTEGRATION_*` / `VALIDATION_*` must not be protected (pipelines run on feature branches). Only `PROD_*` should be protected. Use GitLab environment scope where documented.

## Nginx

Each environment has its own VM and nginx config:

- Integration: `deploy/nginx_integration.conf` (port 80), `nsft_app_integration`
- Validation: `deploy/nginx_validation.conf` (port 80), `nsft_app_validation`
- Production: `deploy/nginx_prod.conf` (port 80), `nsft_app_prod`

Compose publishes port 80 on every environment. All contexts use HTTP session cookies (`SESSION_COOKIE_SECURE = False`).

## Internationalization (i18n) Support

The application uses Flask-Babel. English and French are supported; users switch language from the navigation bar. Catalog files live under `nath_standalone_flask_template/translations/` (`babel.cfg` at the repo root).

### Mark strings for translation

In Python:

```python
from flask_babel import gettext as _

message = _('Your translatable string')
```

In Jinja2 templates:

```html
<h1>{{ _('Welcome to the Dashboard') }}</h1>
```

### Translation workflow (Docker dev)

Local dev runs in Compose (`nsft_app_dev`). **Do not** run Babel in `nsft_db_dev` (Postgres only). Use the **app** container; the project is mounted at `/opt/nath_standalone_flask_template`, so `.po` / `.mo` changes on the host and in the container are the same files.

Add a **shell function** once per terminal (a plain variable does not work: zsh treats `$APP_PY extract` as one command name):

```bash
app_py() {
  docker exec -it nsft_app_dev \
    /opt/env3/nath_standalone_flask_template/bin/python \
    /opt/nath_standalone_flask_template/manage_translations.py "$@"
}
```

Typical cycle after adding `{{ _('...') }}` strings:

```bash
app_py extract    # refresh messages.pot
app_py update     # merge into en/fr .po files
# edit nath_standalone_flask_template/translations/*/LC_MESSAGES/messages.po on the host
app_py compile    # build .mo files; refresh http://localhost:8080
```

One-shot: `app_py all`

Without a function, run the full command each time:

```bash
docker exec -it nsft_app_dev /opt/env3/nath_standalone_flask_template/bin/python \
  /opt/nath_standalone_flask_template/manage_translations.py extract
```

Commands: `extract`, `update`, `compile`, `init <lang>`, `all`.

### Host-only (optional)

If you prefer not to use Docker for Babel:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install Babel
python manage_translations.py all
```

### Add a new language (e.g. Spanish)

1. `app_py init es` (or host `python manage_translations.py init es`)
2. Add `'es': 'Español'` to `LANGUAGES` in `nath_standalone_flask_template/lib/_config.py`
3. Add a navbar link in `nath_standalone_flask_template/templates/base.html`
4. Translate `nath_standalone_flask_template/translations/es/LC_MESSAGES/messages.po`
5. `app_py compile`

### Current languages

- **English (en)** — default
- **French (fr)** — full catalog
