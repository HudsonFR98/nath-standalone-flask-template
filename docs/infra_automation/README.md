# Infra automation — strategy

Goal: remove the manual "create the VM in Proxmox, add the DNS record in Pi-hole, then run the pipeline" step. For every deployed environment the GitLab CI pipeline makes the VM exist, reachable and resolvable, idempotently, **before** Ansible deploys the containers.

The same three infra jobs are stamped out once per environment:

```text
build_docker                       → image pushed to GitLab Container Registry
   │
   ▼  (per environment <env> = integration | validation | prod)
allocate_<env>_ip                  → Pi-hole: reuse or reserve first free IP in 192.168.1.124–200
setup_<env>_vm                     → Terraform: clone the Debian 13 cloud-init template, set IP
                                     (user + SSH keys come from the template), wait for cloud-init + SSH
update_<env>                       → Ansible (runs as `Nath` + sudo)
destroy_<env>_vm                   → Terraform targeted destroy + Pi-hole record removal
```

Run 1 creates everything. Runs 2..n find the VM and the record already exist and do nothing (Terraform plan is empty, Pi-hole record is reused), then `update_<env>` redeploys the containers.

## Environments

| Environment | Purpose | Trigger | Lifecycle |
|---|---|---|---|
| `integration` | disposable test instance, "meant to be broken": the app test suite (`run_tests.py`) runs inside its app container (`test_integration`) | every branch push and every merge request | VM created at the start of the pipeline, **destroyed automatically** after the tests (`destroy_integration_vm`); `INTEGRATION_KEEP_VM=true` makes the destroy manual |
| `validation` | pre-production: identical deployment, no automated tests, for checking a release by hand | every branch push and every merge request, after `test_integration` passed | long-lived; `destroy_validation_vm` is manual |
| `prod` | production | `master` only, after `update_validation`; `allocate_prod_ip`, `setup_prod_vm`, and `update_prod` are **manual** | long-lived; `destroy_prod_vm` is manual |

`dev` (local `docker-compose.yml`) is not part of this flow.

What differs between environments is only data, never code:

| Per environment | Value |
|---|---|
| VM name | `serv-nath-nsft-<env>-NN` |
| FQDN / Pi-hole record | `nsft.integration.nath-server.home`, `nsft.validation.nath-server.home`, `nsft.nath-server.home` |
| GitLab Terraform state | `<env>-vm` |
| dotenv keys between jobs | `<ENV>_VM_IP`, `<ENV>_VM_FQDN`, `<ENV>_VM_ID`, `<ENV>_VM_NAME`, `<ENV>_VM_GENERATION` |
| CI variables | `<ENV>_VM_FQDN`, `<ENV>_POSTGRES_*`, `<ENV>_SECRET_KEY`, `<ENV>_NSFT_DB_NAME`, `<ENV>_ADMIN_USER_*`, `<ENV>_REVIEWER_USER_*`, optional `<ENV>_VM_GENERATION_SEED` |
| Flask context / nginx / inventory group | `lib/_config.py`, `deploy/nginx_<env>.conf`, `[<env>]` in `deploy/ansible/inventory.ini` |
| GitLab environment + `resource_group` | `<env>` / `<env>-infra` |

The IP pool (`IP_POOL_START`/`IP_POOL_END`, default `.124–.200`) is shared: each environment takes the first free address.

## Documents

| File | Content |
|---|---|
| [01_target_architecture.md](01_target_architecture.md) | Current vs target flow, components, network/DNS view, naming |
| [02_terraform_proxmox.md](02_terraform_proxmox.md) | Provider, Proxmox API token, GitLab state backend, HCL for the VM, safety rails, import of an existing VM |
| [03_pihole_dns.md](03_pihole_dns.md) | Pi-hole v6 API, IP allocation algorithm, Python client design |
| [04_gitlab_ci.md](04_gitlab_ci.md) | Stages/jobs per environment, CI variables, artifacts between jobs, gating rules |
| [05_ansible_adaptations.md](05_ansible_adaptations.md) | Changes needed in `deploy/ansible*` for a non-root cloud-init VM, test playbook |
| [06_rollout_and_open_questions.md](06_rollout_and_open_questions.md) | Step-by-step rollout, testing, rollback, security notes, open questions |

## Decisions (summary)

| Topic | Decision | Why |
|---|---|---|
| IaC tool | Terraform (`hashicorp/terraform` image, pulled through the Dependency Proxy) with the `bpg/proxmox` provider | `bpg/proxmox` is the maintained provider with native cloud-init support. OpenTofu is a drop-in swap if you ever want it. |
| One Terraform root per environment | `deploy/terraform/integration`, `validation`, `prod` | Sizing (RAM, disk, cores) differs per environment. Resource addresses stay `proxmox_virtual_environment_vm.app`, so each GitLab state (`<env>-vm`) is reused |
| Terraform state | GitLab-managed Terraform state (HTTP backend), one state per environment: `integration-vm`, `validation-vm`, `prod-vm` | No extra infra, auth with `CI_JOB_TOKEN`, locking included, and destroying integration can never touch prod state |
| VM IP | Chosen by a Python script against Pi-hole, **before** Terraform, and injected into cloud-init via Terraform | The VM boots directly on its final IP; the template's `.108` (`d13t.nath-server.home`) is never used, so several template clones can coexist |
| DNS record | Pi-hole v6 REST API (`/api/config/dns/hosts`) via a small OOP Python client in `deploy/infra/` | Same style as the existing `deploy/ansible_deploy.py`; no extra Terraform provider needed |
| IP reservation | The Pi-hole record itself is the reservation. If the FQDN already exists → reuse its IP | Makes the job idempotent without a separate lock store |
| Safety | Terraform plan is inspected: any `delete`/`replace` of the VM fails the job. Destroy is a separate job: automatic for integration, **manual** for validation and prod | A template change must never silently recreate a long-lived VM |
| VM name | `serv-nath-nsft-<env>-NN`; `NN` kept in Terraform state (`terraform_data`), bumped when a VM is removed and a new one created. Destroy targets the VM only | Naming convention; the counter must outlive the VM and Proxmox forgets deleted VMs. Integration VMs therefore count up (`-01`, `-02`, …) at every pipeline |
| Integration tests | `test_integration` runs `run_tests.py` **inside the deployed app container** through Ansible (`deploy/ansible/run_tests.yml`) | Tests the image that was actually built and deployed, against a real Postgres, with the integration context; no second test harness in CI |
| Validation gate | prod VM, DNS, and deploy jobs are manual | Pre-production must exist before anyone provisions or touches prod |
| SSH / privileges | Ansible connects as `Nath` with `become` (sudo). Root login stays disabled | Matches template 121 (`ciuser: Nath`) |
| Passing data between jobs | `dotenv` artifacts with environment-prefixed keys (`INTEGRATION_VM_IP`, `PROD_VM_IP`, …) | Standard GitLab mechanism, visible in job UI; prefixes keep environments apart in one pipeline |

## What this looks like in the repo

```text
.gitlab-ci.yml                       stages docker / integration / validation / prod; hidden templates
                                     .allocate_ip .setup_vm .destroy_vm .update_app, stamped per env
deploy/
  terraform/
    integration/ validation/ prod/  one root each; sizing defaults in that directory's variables.tf
  infra/                             Python package (OOP)
    const.py                         ENVIRONMENTS, pool defaults, dotenv suffixes
    environment.py                   Environment (dotenv prefix, state name)
    pihole_client.py                 PiholeClient (auth, list hosts, put/delete host)
    ip_allocator.py                  IpAllocator (range scan, reuse existing record)
    plan_guard.py                    TerraformPlanGuard (refuse delete/replace)
    generation.py                    GenerationResolver (VM name counter, from Terraform state)
    ssh_waiter.py                    SshWaiter (wait for port 22 + cloud-init done)
    tests/                           unittest suite (dev only, not run on integration)
  infra_deploy.py                    CLI: allocate-ip | release-ip | next-generation | guard-plan | wait-ssh  (--env)
  ansible/
    inventory.ini                    [integration] [validation] [prod]
    docker_deploy.yml                deploy/update
    run_tests.yml                    run_tests.py inside the app container
  ansible_deploy.py                  --env integration|validation|prod, --action deploy|update|test
lib/_config.py                       Flask context classes (dev, integration, validation, prod)
deploy/nginx_<env>.conf
nath_standalone_flask_template/tests/  Flask pytest suite run by test_integration
docs/infra_automation/               this folder
```

## Before you start

Read [06_rollout_and_open_questions.md](06_rollout_and_open_questions.md) first: it lists the homelab facts that were assumed (Proxmox node name, template VMID, Pi-hole version, how `nath` gets sudo, etc.). Each assumption is tagged `ASSUMPTION` in the other documents so you can grep for them.

One security note now: the `nath` password was shared in chat and appears in the template image. It must not be committed anywhere in this repo (including these docs); treat it as a GitLab masked variable if Ansible needs it for `sudo`, and prefer rotating it once the pipeline works (see 06).
