# 04 — GitLab CI integration

## Stages

```yaml
stages:
  - docker
  - integration
  - validation
  - prod
```

One stage per deployed environment. Inside a stage the jobs are chained with `needs`, so the stage is mostly a grouping for the pipeline view.

```text
build_docker
  └─▶ allocate_integration_ip ─▶ setup_integration_vm ─▶ update_integration ─▶ test_integration ─▶ destroy_integration_vm (always)
                                                                                        │
          every branch push and merge request:                                      ▼
          allocate_validation_ip ─▶ setup_validation_vm ─▶ update_validation           (destroy_validation_vm: manual)
                                                                 │
                                                                 ▼
          master only:
          allocate_prod_ip [manual] ─▶ setup_prod_vm [manual] ─▶ update_prod [manual]   (destroy_prod_vm: manual)
```

## Trigger policy

| Environment | Jobs run when | Deploy | Destroy |
|---|---|---|---|
| integration | every branch push and every merge request | automatic | automatic after `test_integration` (also when the tests failed). `INTEGRATION_KEEP_VM=true` → manual |
| validation | same as integration, after `test_integration` succeeded | automatic | manual |
| prod | `master` only (`$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH`), after `update_validation` | **manual** (`allocate_prod_ip`, `setup_prod_vm`, `update_prod`) | manual |

A branch that already has an open merge request runs the merge-request pipeline only (`workflow:rules`), so the same push does not build two integration VMs. Jobs with no `rules` are omitted from merge-request pipelines, so every job extends `.rules_branch_and_mr` or `.rules_master`. `destroy_integration_vm` used to use a bare `when: always`, which added it to the merge-request pipeline while `test_integration` (no rules) was left out, and GitLab refused to create the pipeline.

Consequence: **integration** and **validation** both run on every branch and merge request. Shared vars (`PROXMOX_VE_*`, `PIHOLE_*`, `GITLAB_CA_FILE`, `TELEGRAM_*`) and all `INTEGRATION_*` / `VALIDATION_*` must **not** be *protected*, or feature-branch pipelines get empty values (e.g. missing `VM_FQDN`). Only `PROD_*` should be protected. Use GitLab environment scope (`integration`, `validation`, `prod`) on per-env secrets when needed.

If `setup_integration_vm` or `update_integration` fails, `test_integration` is skipped and so is `destroy_integration_vm`: the half-provisioned VM stays for inspection and the next pipeline converges it (same FQDN, same IP, plan guard still active).

## CI/CD variables (Settings → CI/CD → Variables)

Shared:

| Variable | Masked | Protected | Value |
|---|---|---|---|
| `PROXMOX_VE_ENDPOINT` | no | no | `https://<pve-host>:8006/` |
| `PROXMOX_VE_API_TOKEN` | yes | no | `terraform@pve!ci=<uuid>` |
| `PROXMOX_VE_INSECURE` | no | no | `true` (self-signed cert) |
| `PIHOLE_URL` | no | no | `http://192.168.1.105` |
| `PIHOLE_APP_PASSWORD` | yes | no | Pi-hole *application password* |
| `GITLAB_CA_FILE` | no (File) | no | public cert of the self-signed GitLab |
| `IP_POOL_START` / `IP_POOL_END` | no | no | optional, default `192.168.1.124` / `192.168.1.200`; one pool for all environments |
| `IP_POOL_RESERVED` | no | no | optional comma list of IPs to never pick |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | yes / no | no | shared by all environments |
| `INTEGRATION_KEEP_VM` | no | no | optional, `true` to make `destroy_integration_vm` manual |

Per environment, `<ENV>` ∈ {`INTEGRATION`, `VALIDATION`, `PROD`}:

| Variable | Masked | Protected | Value |
|---|---|---|---|
| `<ENV>_PROXMOX_NODE_NAME` | no | prod only | Proxmox node for that environment (e.g. `proxmox2`, `nath-server`) |
| `<ENV>_PROXMOX_TEMPLATE_VM_ID` | no | prod only | cloud-init template VMID on that node |
| `<ENV>_PROXMOX_DATASTORE_ID` | no | prod only | datastore on that node (e.g. `local-lvm`) |
| `<ENV>_PROXMOX_NETWORK_BRIDGE` | no | prod only | optional. Proxmox bridge for the VM NIC (`vmbr0`, `vmbr1`, …). Default `vmbr0` when unset |
| `<ENV>_GATEWAY` | no | prod only | optional. Cloud-init default gateway for the VM. Default `192.168.1.1` in Terraform when unset (set when using another bridge/L3, e.g. `vmbr1` → `10.20.40.1`) |
| `<ENV>_VM_IP` | no | prod only | optional. When set, Pi-hole and Terraform use this address and do not scan the pool |
| `<ENV>_VM_FQDN` | no | prod only | FQDNs in `deploy/ansible/inventory.ini` and nginx `server_name` |
| `<ENV>_VM_GENERATION_SEED` | no | prod only | optional, default `1` |
| `<ENV>_POSTGRES_USER`, `<ENV>_POSTGRES_PASSWORD`, `<ENV>_POSTGRES_DB`, `<ENV>_NSFT_DB_NAME` | password: yes | prod only | Postgres and app database for that environment |
| `<ENV>_SECRET_KEY` | yes | prod only | |
| `<ENV>_ADMIN_USER_USERNAME`, `_PASSWORD`, `_EMAIL`, `_FIRST_NAME`, `_LAST_NAME` | password: yes | prod only | admin user created by the app |
| `<ENV>_REVIEWER_USER_*` (optional) | password: yes on `_PASSWORD` | as needed | bootstrap reviewer only when `_USERNAME` and `_PASSWORD` are both set |
| `<ENV>_ANSIBLE_BECOME_PASSWORD` | yes | — | only if `Nath` has no passwordless sudo (see 05) |

Scope a variable to its GitLab environment (`integration` / `validation` / `prod`) when you prefer the same name with different values; every job declares its `environment:`.

`PROXMOX_VE_*` are read natively by the provider. Everything else is passed as `TF_VAR_*`, exported in `before_script`, or given as CLI flags.

## Job templates

The real file uses `extends:` (deep merge) rather than YAML anchors, so per-environment jobs only add variables.

```yaml
.terraform:
  image: { name: $DEP_PROXY_PREFIX/hashicorp/terraform:1.16, entrypoint: [""] }
  variables:
    TF_ROOT: deploy/terraform/${ENV_NAME}   # integration | validation | prod
    TF_HTTP_USERNAME: gitlab-ci-token
    TF_HTTP_PASSWORD: ${CI_JOB_TOKEN}
    # ...TF_IN_AUTOMATION, TF_INPUT, lock methods
  before_script:
    - apk add --no-cache python3 openssh-client
    - export ENV_PREFIX=$(printf '%s' "$ENV_NAME" | tr 'a-z-' 'A-Z_')
    - export TF_VAR_node_name="$(printenv "${ENV_PREFIX}_PROXMOX_NODE_NAME")"
    - export TF_VAR_template_vm_id="$(printenv "${ENV_PREFIX}_PROXMOX_TEMPLATE_VM_ID")"
    - export TF_VAR_datastore_id="$(printenv "${ENV_PREFIX}_PROXMOX_DATASTORE_ID")"
    - |
      network_bridge="$(printenv "${ENV_PREFIX}_PROXMOX_NETWORK_BRIDGE" || true)"
      if [ -n "$network_bridge" ]; then export TF_VAR_network_bridge="$network_bridge"; fi
    - |
      lan_gateway="$(printenv "${ENV_PREFIX}_GATEWAY" || true)"
      if [ -n "$lan_gateway" ]; then export TF_VAR_gateway="$lan_gateway"; fi
    - export TF_STATE_NAME="${ENV_NAME}-vm"                      # integration-vm | validation-vm | prod-vm
    - export TF_HTTP_ADDRESS="${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/terraform/state/${TF_STATE_NAME}"
    - export TF_HTTP_LOCK_ADDRESS="${TF_HTTP_ADDRESS}/lock"
    - export TF_HTTP_UNLOCK_ADDRESS="${TF_HTTP_ADDRESS}/lock"
    - export TF_VAR_env="$ENV_NAME"
    - export TF_VAR_fqdn="$VM_FQDN"
    - cd $TF_ROOT && terraform init -input=false -reconfigure
```

Everything derived from the environment name is computed in shell from `ENV_NAME`, so no nested `${…}` expansion is needed in `variables:`.

## Job 1 — `allocate_<env>_ip`

```yaml
.allocate_ip:
  extends: .infra_python
  script:
    - python3 deploy/infra_deploy.py allocate-ip
        --env "$ENV_NAME" --fqdn "$VM_FQDN"
        --pool-start "${IP_POOL_START:-}" --pool-end "${IP_POOL_END:-}" --reserved "${IP_POOL_RESERVED:-}"
        --fixed-ip "${VM_IP:-}"
        --output infra.env
  artifacts:
    reports:
      dotenv: infra.env        # <ENV>_VM_IP, <ENV>_VM_FQDN, <ENV>_VM_IP_REUSED

allocate_prod_ip:
  extends: [.allocate_ip, .rules_branch_and_mr]
  stage: prod
  needs: [update_validation]
  variables: { ENV_NAME: prod, VM_FQDN: $PROD_VM_FQDN }
  environment: { name: prod, action: prepare }
```

Empty pool arguments fall back to the defaults in `deploy/infra/const.py`. `VM_IP` is `$<ENV>_VM_IP`. When that variable is set, the allocator writes that address into Pi-hole and does not scan the pool. When it is empty, the first free address is chosen as before. The dotenv artifact still publishes `<ENV>_VM_IP` for Terraform.

## Job 2 — `setup_<env>_vm`

```yaml
.setup_vm:
  extends: .terraform
  script:
    - terraform validate
    - |
      if terraform state list | grep -qx 'proxmox_virtual_environment_vm.app'; then
        terraform apply -refresh-only -input=false -auto-approve
      fi
    - terraform show -json > state.json
    - export TF_VAR_vm_generation=$(python3 .../infra_deploy.py next-generation --env "$ENV_NAME" --state-json state.json --seed "${VM_GENERATION_SEED:-1}")
    - terraform plan -input=false -out=tfplan -detailed-exitcode   # 0 no change, 1 error, 2 changes
    - terraform show -json tfplan > tfplan.json
    - python3 .../infra_deploy.py guard-plan --plan-json tfplan.json
    - if [ "$plan_rc" = "2" ]; then terraform apply -input=false -auto-approve tfplan; fi
    - |
      cat > ${CI_PROJECT_DIR}/vm.env <<EOF
      ${ENV_PREFIX}_VM_ID=$(terraform output -raw vm_id)
      ${ENV_PREFIX}_VM_NAME=$(terraform output -raw vm_name)       # serv-nath-nsft-<env>-NN
      ${ENV_PREFIX}_VM_IP=$(terraform output -raw vm_ip)
      ${ENV_PREFIX}_VM_FQDN=$(terraform output -raw fqdn)
      ${ENV_PREFIX}_VM_GENERATION=$(terraform output -raw generation)
      EOF
    - python3 .../infra_deploy.py wait-ssh --host "$(terraform output -raw vm_ip)" --user Nath --key ~/.ssh/id_rsa --timeout 600 --cloud-init-wait
  artifacts:
    reports: { dotenv: vm.env }

setup_prod_vm:
  extends: [.setup_vm, .rules_branch_and_mr]
  stage: prod
  needs: [{ job: allocate_prod_ip, artifacts: true }]
  variables:
    ENV_NAME: prod
    VM_FQDN: $PROD_VM_FQDN
    TF_VAR_vm_ip: ${PROD_VM_IP}                       # from the allocate dotenv
    VM_GENERATION_SEED: ${PROD_VM_GENERATION_SEED}
  environment: { name: prod, action: prepare }
  resource_group: prod-infra
```

`SshWaiter.wait()` loops on TCP 22, then runs `cloud-init status --wait` over SSH as `Nath` until done. This guarantees that `update_<env>` finds a fully initialised VM (user, keys, network) and not a half-booted one.

`resource_group: <env>-infra` serialises the Terraform jobs of one environment across pipelines; GitLab's state locking is the second line of defence.

## Job 3 — `update_<env>`

```yaml
.update_app:
  extends: .ssh_setup
  variables: { BUILD_DATE: $CI_PIPELINE_CREATED_AT }
  script:
    - python3 deploy/ansible_deploy.py --action update --env "$ENV_NAME" --ansible-user Nath
        --docker-image $DOCKER_IMAGE ...
        --postgres-password "$(printenv "${ENV_PREFIX}_POSTGRES_PASSWORD")" ...

update_validation:
  extends: [.update_app, .rules_branch_and_mr]
  stage: validation
  needs: [build_docker, { job: setup_validation_vm, artifacts: true }]
  variables:
    ENV_NAME: validation
    SSH_HOST: nsft.validation.nath-server.home       # ssh-keyscan + inventory group host
  environment: { name: validation, url: https://nsft.validation.nath-server.home }
```

`ENV_PREFIX` is `VALIDATION`. The script reads `VALIDATION_POSTGRES_PASSWORD` (and the other `<ENV>_*` secrets) with `printenv` when the job runs. Do not copy them in `variables:`: GitLab expands that block before it injects a variable scoped to the `validation` environment, so the copy is empty and Ansible reports `validation_postgres_password` missing. Masking only hides the value in the log.

`ssh-keyscan` and Ansible both use the FQDN. The IP stays an infra concern (`allocate_<env>_ip` / Terraform / `wait-ssh`); it is not passed into Ansible. See 05.

## Job 4 — `test_integration` (integration only)

```yaml
test_integration:
  extends: .ssh_setup
  stage: integration
  needs: [update_integration]
  variables: { ENV_NAME: integration, SSH_HOST: nsft.integration.nath-server.home }
  script:
    - python3 deploy/ansible_deploy.py --action test --env "$ENV_NAME" --ansible-user Nath
  environment: { name: integration, action: prepare }
```

`--action test` runs `deploy/ansible/run_tests.yml`: `docker exec` of `budget_manager/tests/run_tests.py` inside `nsft_app_integration`, with the container's own environment (integration context and its Postgres). The suite is pytest. The job fails when the suite fails, which blocks `validation` and `prod`. `--test-labels` is forwarded as extra pytest arguments when set.

The infra unit tests (`deploy/infra/tests`) are not part of this job; they are run by developers (`cd deploy && python3 -m unittest discover -s infra/tests -t .`).

## Job 5 — `destroy_<env>_vm`

```yaml
.destroy_vm:
  extends: .terraform
  variables: { TF_VAR_vm_ip: "0.0.0.0", TF_VAR_vm_generation: "1" }   # required by the module, irrelevant for -target
  script:
    # -target: remove the VM only. terraform_data.generation stays in state so the next VM is numbered N+1.
    - terraform destroy -input=false -auto-approve -target=proxmox_virtual_environment_vm.app
    - python3 .../infra_deploy.py release-ip --fqdn "$VM_FQDN"

destroy_integration_vm:
  extends: .destroy_vm
  stage: integration
  needs: [test_integration]
  rules:
    - if: $INTEGRATION_KEEP_VM == "true"
      when: manual
      allow_failure: true
    - when: always
  variables: { ENV_NAME: integration, VM_FQDN: $INTEGRATION_VM_FQDN }
  environment: { name: integration, action: stop }
  resource_group: integration-infra

destroy_prod_vm:
  extends: [.destroy_vm, .rules_master_manual]
  stage: prod
  needs: []
  variables: { ENV_NAME: prod, VM_FQDN: $PROD_VM_FQDN }
  environment: { name: prod, action: stop }
  resource_group: prod-infra
```

For validation and prod this is the only path that deletes anything. Postgres data lives on the VM disk, so destroying the VM destroys that environment's database: make a backup first (the app already writes to `/var/backups/...`; copy it off-VM before pressing the button). Integration data is disposable by definition.

Never replace the `-target` form with a bare `terraform destroy`: that would also wipe the generation counter and the next VM would be numbered `-01` again.

## Failure behaviour

| Failure | Effect |
|---|---|
| Pi-hole unreachable / bad password | `allocate_<env>_ip` fails; nothing created |
| No free IP | `allocate_<env>_ip` fails with the scanned pool listed |
| Plan wants to delete/replace | `setup_<env>_vm` fails at guard; VM untouched |
| Clone fails mid-way | Terraform marks the resource tainted; next run retries. Check Proxmox for a half-created VM |
| cloud-init never finishes | `wait-ssh` times out (10 min); VM exists, investigate via Proxmox console; rerun pipeline |
| Ansible fails | as today |
| `test_integration` red | pipeline fails, validation/prod are not reached, `destroy_integration_vm` still runs |

## Runner requirements

- Network: the Docker executor must reach `<pve>:8006`, `192.168.1.105:80`, the LAN pool `.124–.200` (SSH + ICMP), and GitLab.
- `/runner-ssh/id_rsa` is already mounted. Its public counterpart must be in the **template** cloud-init SSH keys (already done). Terraform does not inject keys.
- Images pulled through the Dependency Proxy: `python:3.11-slim`, `hashicorp/terraform:1.16`. Both are on Docker Hub.
- Three VMs may exist at once (integration while a pipeline runs, validation, prod): size the Proxmox node and the IP pool accordingly.
