# Ansible Deployment Structure

This directory contains the modularized Ansible deployment configuration for the nath_standalone_flask_template application.

## Structure

```
deploy/ansible/
├── docker_deploy.yml          # Deploy / update the stack
├── run_tests.yml              # Pytest inside the deployed app container
├── inventory.ini              # [integration] [validation] [prod]
├── requirements.yml           # Ansible dependencies
├── README.md                 # This file
└── roles/                    # Modular roles
    ├── docker/               # Docker installation
    │   └── tasks/main.yml
    ├── directories/          # Directory and permission setup
    │   └── tasks/main.yml
    ├── registry/             # Docker registry authentication
    │   └── tasks/main.yml
    ├── files/                # File copying tasks
    │   └── tasks/main.yml
    ├── containers/           # Container management
    │   └── tasks/main.yml
    └── verification/         # Verification and testing
        └── tasks/main.yml
```

## Roles Description

### docker
- Installs Docker dependencies and packages
- Adds Docker repository and GPG key
- Installs Docker CE and related tools
- Installs PostgreSQL client

### directories
- Creates necessary directories for logs, data, and configuration
- Sets proper permissions for Docker containers
- Creates log files with correct ownership

### registry
- Installs the GitLab CA (`gitlab_ca_file` / `GITLAB_CA_FILE`) for Docker and the system trust store
- Logs in to the GitLab Container Registry and the Dependency Proxy

### files
- Copies initialization scripts to the remote server
- Copies the SQL reset script
- Copies `deploy/nginx_<context>.conf`

### containers
- Renders Compose and starts PostgreSQL, Redis, the app, and nginx
- Publishes port 80 on every environment
- Keeps the database volume on `update`

### verification
- Checks that nginx answers on port 80 (`/health` returns 200)

Integration tests are a separate playbook, `run_tests.yml`, invoked with `ansible_deploy.py --action test`.

## Usage

The main playbook `docker_deploy.yml` now uses a modular approach with roles instead of inline tasks. This provides:

- **Better organization**: Each role has a specific responsibility
- **Easier maintenance**: Changes to specific functionality are isolated
- **Reusability**: Roles can be reused in other playbooks
- **Readability**: The main playbook is much shorter and clearer

## Benefits of Modularization

1. **Maintainability**: Each role focuses on a specific aspect of deployment
2. **Reusability**: Roles can be used independently or in different combinations
3. **Testing**: Individual roles can be tested separately
4. **Documentation**: Each role is self-documenting through its structure
5. **Version Control**: Changes to specific functionality are easier to track

## Original vs New Structure

**Before**: Single 284-line file with all tasks mixed together
**After**: 6 focused roles with clear responsibilities, plus a concise main playbook

This modular approach makes the deployment process more maintainable and easier to understand. 