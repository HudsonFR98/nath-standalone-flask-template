# 05 — Ansible adaptations

The Ansible roles do not change functionally. What changes is *how* Ansible reaches the VM and *as whom*.

## 1. Non-root connection

Today (`deploy/ansible/docker_deploy.yml`):

```yaml
  remote_user: root
  become: yes
```

Target:

```yaml
  remote_user: "{{ ansible_user | default('Nath') }}"
  become: yes            # sudo for every task (apt, docker, chown ...)
```

`become: yes` with the default `become_method: sudo` needs `nath` to run `sudo` without a password prompt. Two options:

| Option | How | Recommendation |
|---|---|---|
| A. Passwordless sudo in the template | `/etc/sudoers.d/90-cloud-init-users` → `Nath ALL=(ALL) NOPASSWD:ALL` (template 121 uses `ciuser: Nath` — Linux usernames are case-sensitive) | Preferred: no password in CI |
| B. Pass the sudo password | CI variable `<ENV>_ANSIBLE_BECOME_PASSWORD`, passed as `-e ansible_become_password=...` | Fallback only |

`ASSUMPTION: option A works` — please confirm with `sudo -n true` as `nath` on a fresh clone.

## 2. Inventory stays FQDN-only

`deploy/ansible/inventory.ini` has one group per deployed environment; the group name is the Flask context and the `--env` value of `ansible_deploy.py`. Ansible SSHs to the FQDN. Pi-hole already has the record (created or reused in `allocate_<env>_ip`); resolver cache on the LAN is fine, so there is no `ansible_host` IP override.

```ini
[integration]
nsft.integration.nath-server.home

[validation]
nsft.validation.nath-server.home

[prod]
nsft.nath-server.home
```

The FQDNs must match the `<ENV>_VM_FQDN` CI variables and the `server_name` in `deploy/nginx_<env>.conf`.

## 3. `deploy/ansible_deploy.py`

Extra flags (user / sudo only — no host override):

```python
parser.add_argument("--ansible-user", default="Nath", help="SSH user")
parser.add_argument("--become-password", help="sudo password if the user has no NOPASSWD sudo")
...
cmd.extend(["-e", f"ansible_user={args.ansible_user}"])
if args.become_password:
    cmd.extend(["-e", f"ansible_become_password={args.become_password}"])
```

`--env` accepts `integration | validation | prod` (from `deploy/infra/const.py`). `--action` selects the playbook:

| action | playbook | needs `--docker-image` |
|---|---|---|
| `deploy`, `update` | `ansible/docker_deploy.yml` (roles docker → directories → registry → files → containers → verification) | yes |
| `test` | `ansible/run_tests.yml` | no |

`SSH_HOST` in CI is the environment's FQDN (`nsft.integration.nath-server.home`, `nsft.validation.nath-server.home`, `nsft.nath-server.home`).

## 3b. `deploy/ansible/run_tests.yml` (integration)

Runs the Flask pytest suite **inside the app container that `docker_deploy.yml` just started**, so the test target is the exact image, settings and Postgres of the environment:

```yaml
- ansible.builtin.command:
    argv:
      - docker
      - exec
      - --workdir
      - /opt/nath_standalone_flask_template
      - nsft_app_integration
      - /opt/env3/nath_standalone_flask_template/bin/python
      - nath_standalone_flask_template/tests/run_tests.py
```

A successful `command` task only logs `ok`, so the play registers the result and prints `stdout` with the `debug` module. `ansible_deploy.py` sets `ANSIBLE_CALLBACK_RESULT_FORMAT=yaml` for `--action test`, which keeps the line breaks. The default JSON result format would show them as `\n`.

The play checks that the container is running and fails when `run_tests.py` exits non-zero. It never restarts containers or touches volumes. The suite runs pytest against the environment's Postgres (`NSFT_DB_NAME`) using the container's existing credentials.

## 4. SSH host keys

`.ssh_setup_template` already does `ssh-keyscan -H "$SSH_HOST"` against the FQDN. Because the VM is recreated from scratch when destroyed, host keys change; the runner's `known_hosts` is per-job, so no stale-key problem.

## 5. UID collision worth knowing

The roles chown data/log directories to UID/GID `1000` (the `web` user inside the container). On the new template, `nath` is almost certainly UID 1000 too. Consequence: `/opt/nath_standalone_flask_template_data`, logs and backups will appear as owned by `nath` on the host. This is harmless (same numeric ID as the container's `web`), but it means `nath` can read the app data — acceptable for an admin account. If you would rather separate them, create a dedicated `web` user with a fixed UID (e.g. `1500`) via cloud-init and change the `1000` constants in `roles/directories/tasks/main.yml` and the `Dockerfile`.

## 6. Optional: move OS provisioning to cloud-init

The `docker` role installs Docker CE via apt on every run (idempotent but ~1 min). Since the VM is now cloud-init driven, you could bake Docker into the template or install it via a `vendor_data` snippet, and keep the role only as a safety net. Not required for the first iteration; the current role already works on a fresh Debian.

`ASSUMPTION: Debian 13 (trixie)`. The `docker` role hard-codes the `bookworm` apt repository. On trixie use `trixie stable` (or `$(. /etc/os-release && echo $VERSION_CODENAME)`), otherwise apt will install the bookworm build, which works today but is the wrong channel. Change:

```yaml
repo: deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian {{ ansible_distribution_release }} stable
```

## 7. Nothing else changes

Roles `directories`, `registry`, `files`, `containers`, and `verification` follow the same shape on every environment. Container names are `nsft_{app,db,redis,nginx}_<env>`. Nginx listens on port 80 in every environment. `roles/files` copies `deploy/nginx_<env>.conf`.
