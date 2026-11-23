# 02 — Terraform + Proxmox

## Provider choice

`bpg/proxmox` (Terraform Registry: `registry.terraform.io/providers/bpg/proxmox`).

- Actively maintained, supports Proxmox VE 8 and 9.
- Native cloud-init through the `initialization` block: IP, gateway, DNS — no snippet upload, no SSH access to the Proxmox host needed. User and SSH keys stay on the template.
- Clone from a template with `clone { vm_id = ... }`.

Not chosen: `Telmate/proxmox` (older, slower releases, cloud-init handling less predictable).

The provider is pinned to `~> 0.114` in each `deploy/terraform/<env>/versions.tf`; bump it deliberately after a local `terraform plan`, never float on `latest` in CI.

## Proxmox prerequisites (one-off, manual)

### 1. Dedicated user + API token

```bash
# On the Proxmox node (PVE 9+: VM.Monitor was removed — do not use it)
pveum user add terraform@pve --comment "GitLab CI Terraform"
pveum role add TerraformProv -privs "Datastore.AllocateSpace Datastore.Audit Pool.Allocate SDN.Use Sys.Audit Sys.Console Sys.Modify VM.Allocate VM.Audit VM.Clone VM.Config.CDROM VM.Config.CPU VM.Config.Cloudinit VM.Config.Disk VM.Config.HWType VM.Config.Memory VM.Config.Network VM.Config.Options VM.Migrate VM.PowerMgmt VM.GuestAgent.Audit"
pveum aclmod / -user terraform@pve -role TerraformProv
pveum user token add terraform@pve ci --privsep 0
# → copy "full-tokenid" (terraform@pve!ci) and "value" into GitLab CI variables
```

On **Proxmox VE 9**, `VM.Monitor` no longer exists. Guest-agent read access uses `VM.GuestAgent.Audit` instead. If Terraform later returns `403` on clone or config changes, add missing privileges from `pveum role list` / Datacenter → Permissions → Roles, or temporarily assign the built-in `PVEVMAdmin` role to `terraform@pve` to see what is missing, then trim back.

`--privsep 0` makes the token inherit the user's permissions. Store as:

- `PROXMOX_VE_ENDPOINT` = `https://<pve-host>:8006/`
- `PROXMOX_VE_API_TOKEN` = `terraform@pve!ci=<uuid>` (masked)
- `PROXMOX_VE_INSECURE` = `true` if the PVE certificate is self-signed (default in a homelab)

The provider reads these env vars directly, so no credentials appear in HCL.

### 2. Template requirements

The Debian 13 cloud-init template must have:

- a cloud-init drive on **`sata1`** (this template; Proxmox docs often show `ide2`, but UEFI/OVMF templates commonly use SATA or SCSI instead)
- `qemu-guest-agent` installed and enabled — `ASSUMPTION: yes` (if not, set `agent.enabled = false` and `stop_on_destroy = true`, see below)
- user `nath` and the gitlab-runner public key already set in the template's cloud-init tab (`ciuser` / `sshkeys`). Terraform does **not** override them. To change keys later: edit the template in Proxmox (Cloud-Init → SSH public keys), then convert/update the template. Existing clones keep the old keys until they are destroyed and recreated.
- `cloud-init clean` run before converting to template so cloud-init re-runs on first boot of each clone (Proxmox also changes the instance-id on clone, which triggers a re-run) — `ASSUMPTION: yes`
- static IP `.108` (`d13t.nath-server.home`) configured **through the Proxmox cloud-init tab (`ipconfig0`)**, not baked into `/etc/network/interfaces` — `ASSUMPTION`. If it is baked in the image, cloud-init cannot override it and the design must fall back to "boot on .108, then re-IP" (see 06).

### Cloud-init drive: `sata1` and no size

In Proxmox, the cloud-init drive is **not a normal disk**. It is a special volume of type `cloudinit` (shown in the GUI as "CloudInit Drive", often with `media=cdrom`). Proxmox generates a tiny NoCloud ISO from the Cloud-Init tab fields (`ciuser`, `sshkeys`, `ipconfig0`, …) and attaches it like a CD-ROM. That is why the UI shows **no size**: there is nothing to allocate in GiB; it is metadata, not storage for the OS or data.

On template **121** (`template-ci-debian-13`, DNS `d13t.nath-server.home`) it sits on **`sata1`**: `sata1: local-lvm:vm-121-cloudinit,media=cdrom`. The OS disk is **`sata0`** (16G), not `scsi0`. Boot order is `sata0;net0`. What matters for Terraform: `initialization.interface = "sata1"` and any disk resize uses `interface = "sata0"`.

Check on the template:

```bash
qm config <template-vmid> | grep -E '^(sata|ide|scsi)[0-9]+.*cloudinit'
# → sata1: local-lvm:vm-XXXX-cloudinit,media=cdrom
```

Do **not** add a `size = …` block for this drive in Terraform. The provider's `initialization` block only points at the existing cloud-init slot; Proxmox owns the volume.

## State backend: GitLab-managed Terraform state

GitLab 18 removed the `Terraform.gitlab-ci.yml` templates and the `gitlab-terraform` image, but the state backend is still supported for both Terraform and OpenTofu.

```hcl
# deploy/terraform/prod/versions.tf (same block in integration/ and validation/)
terraform {
  required_version = ">= 1.6"

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.114"  # 0.114.0 validated Sep 2026
    }
  }

  backend "http" {}   # all values come from TF_HTTP_* env vars set in CI
}

provider "proxmox" {
  # endpoint / api_token / insecure read from PROXMOX_VE_* env vars
}
```

In CI (see 04):

```bash
TF_STATE_NAME="${ENV_NAME}-vm"      # integration-vm | validation-vm | prod-vm: one state per environment
TF_HTTP_ADDRESS="${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/terraform/state/${TF_STATE_NAME}"
TF_HTTP_LOCK_ADDRESS="${TF_HTTP_ADDRESS}/lock"
TF_HTTP_UNLOCK_ADDRESS="${TF_HTTP_ADDRESS}/lock"
TF_HTTP_LOCK_METHOD=POST
TF_HTTP_UNLOCK_METHOD=DELETE
TF_HTTP_RETRY_WAIT_MIN=5
TF_HTTP_USERNAME=gitlab-ci-token
TF_HTTP_PASSWORD=${CI_JOB_TOKEN}
```

The state is browsable under **Operate → Terraform states** in the project. For local runs, use a Personal Access Token with `api` scope as `TF_HTTP_PASSWORD` and your username as `TF_HTTP_USERNAME`.

## HCL

### variables.tf

```hcl
variable "env"              { type = string  default = "prod" }  # pinned per root: integration/, validation/, prod/
variable "app_short"        { type = string  default = "nsft" }
variable "name_prefix"      { type = string  default = "serv-nath" }   # homelab naming convention
variable "vm_generation"    { type = number }              # from infra_deploy.py next-generation (TF_VAR_vm_generation), see "VM naming"
variable "node_name"        { type = string }              # ASSUMPTION: single node, e.g. "pve"
variable "template_vm_id"   { type = number }              # Debian 13 cloud-init template VMID
variable "vm_id"            { type = number  default = null } # let Proxmox pick unless you want a fixed one
variable "datastore_id"     { type = string  default = "local-lvm" }
variable "network_bridge"   { type = string  default = "vmbr0" }
variable "cloudinit_interface" { type = string default = "sata1" }  # template 121: sata1:…:cloudinit
variable "os_disk_interface"   { type = string default = "sata0" }  # template 121: sata0 (not scsi0)

variable "vm_ip"            { type = string }              # from allocate_<env>_ip (TF_VAR_vm_ip)
variable "cidr_bits"        { type = number  default = 24 }
variable "gateway"          { type = string  default = "192.168.1.1" }
variable "dns_server"       { type = string  default = "192.168.1.105" }
variable "dns_domain"       { type = string  default = "nath-server.home" }

variable "cores"            { type = number  default = 2 }
variable "memory_mb"        { type = number  default = 4096 }
variable "disk_gb"          { type = number  default = 40 }
variable "agent_enabled"    { type = bool    default = true }
```

### main.tf

```hcl
locals {
  generation = format("%02d", var.vm_generation)                 # 1 → "01"
  vm_name    = "${var.name_prefix}-${var.app_short}-${var.env}-${local.generation}"   # serv-nath-nsft-prod-01
  fqdn       = var.env == "prod" ? "${var.app_short}.${var.dns_domain}" : "${var.app_short}.${var.env}.${var.dns_domain}"
}

# Memory of the generation counter. Lives in the state, NOT tied to the VM's lifecycle:
# destroy_<env>_vm removes only the VM (-target), so this survives and the next VM gets N+1.
resource "terraform_data" "generation" {
  input = var.vm_generation
}

resource "proxmox_virtual_environment_vm" "app" {
  name        = local.vm_name
  description = "Managed by Terraform (GitLab CI, state ${var.app_short}-${var.env}, generation ${local.generation}). Do not edit by hand."
  tags        = ["ci", var.app_short, var.env]
  node_name   = var.node_name
  vm_id       = var.vm_id

  clone {
    vm_id        = var.template_vm_id
    full         = true
    datastore_id = var.datastore_id
    retries      = 3
  }

  agent {
    enabled = var.agent_enabled
  }
  stop_on_destroy = !var.agent_enabled

  cpu {
    cores = var.cores
    # Omit `type` or set `host` to match template 121 and avoid perpetual plan diffs.
  }

  memory {
    dedicated = var.memory_mb
  }

  # Resize the cloned OS disk. Interface must match the template (121 → sata0).
  disk {
    datastore_id = var.datastore_id
    interface    = var.os_disk_interface
    size         = var.disk_gb
    discard      = "on"
    iothread     = true
  }

  network_device {
    bridge = var.network_bridge
  }

  initialization {
    interface    = var.cloudinit_interface   # sata1 on the d13t template
    datastore_id = var.datastore_id

    ip_config {
      ipv4 {
        address = "${var.vm_ip}/${var.cidr_bits}"
        gateway = var.gateway
      }
    }

    dns {
      servers = [var.dns_server]
      domain  = var.dns_domain
    }

    # Do NOT set user_account. The template already defines ciuser=nath, password, and sshkeys.
    # Setting user_account here would replace those and wipe the template keys.
  }

  started = true
  on_boot = true

  lifecycle {
    # A template refresh must never recreate prod behind our back.
    ignore_changes = [
      clone,            # template VMID or datastore change → we decide manually
      tags,             # Proxmox sorts tags → perpetual diff otherwise
    ]
  }
}
```

Notes:

- `ignore_changes = [clone]` means that if you build a new template with a new VMID and bump `template_vm_id`, Terraform will **not** replace the VM. Rebuilding a long-lived VM (validation, prod) on a new template is an explicit action: manual `destroy_<env>_vm` job, then a normal pipeline. Integration picks the new template up by itself at the next pipeline since it is recreated every time.
- `hostname`: Proxmox's native cloud-init uses `name` as the guest hostname, so the VM will call itself `serv-nath-nsft-prod-01`. That is fine: nothing in Ansible or the app depends on the hostname, only on the FQDN `nsft.nath-server.home`. If you want a short hostname anyway, pass a small `vendor_data_file_id` snippet with `hostname: nsft` (requires the `snippets` content type on a datastore).
- `name` is updated in place by the provider (no replace), so a naming-convention change on a live VM is safe; the generation counter never changes for a live VM anyway (see below).
- The `disk` block only resizes; it does not replace the template disk. If you do not want to touch the disk at all, drop the block and keep the template size.
- No `ssh {}` block in the provider: we do not upload snippets, so the provider never needs SSH to the PVE host.

### outputs.tf

```hcl
output "vm_id"         { value = proxmox_virtual_environment_vm.app.vm_id }
output "vm_name"       { value = proxmox_virtual_environment_vm.app.name }   # serv-nath-nsft-prod-01
output "vm_generation" { value = terraform_data.generation.output }
output "vm_ip"         { value = var.vm_ip }
output "fqdn"          { value = local.fqdn }
```

`setup_<env>_vm` turns these into a dotenv artifact (`<ENV>_VM_ID`, `<ENV>_VM_NAME`, ...) for `update_<env>`.

## VM naming and the generation counter

Convention: `serv-nath-<app_short>-<env>-<NN>` → `serv-nath-nsft-prod-01`. `NN` increments each time the VM is removed and a new one is created; it never changes while a VM lives.

### Where the counter lives

| Candidate | Verdict |
|---|---|
| Ask Proxmox for the highest `serv-nath-nsft-prod-*` | No: a destroyed VM leaves no trace, so `01` would be reused |
| GitLab project CI variable updated via API | Works, but needs a project access token with `api` scope in the pipeline |
| **`terraform_data.generation` in the Terraform state** | Chosen: no extra credential, same state as the VM, visible in `terraform output` |

The only rule this imposes: **never run a full `terraform destroy`** on this state. The `destroy_<env>_vm` jobs (automatic for integration, manual otherwise) run `terraform destroy -target=proxmox_virtual_environment_vm.app`, which removes the VM and keeps `terraform_data.generation`.

### How the next number is computed

`infra_deploy.py next-generation --env <env>` runs in `setup_<env>_vm` right after `terraform init`, before `plan`:

```text
# refresh-only only if the VM is still in state. After destroy -target it is already
# gone; refresh-only then fails with "Cannot apply non-applyable plan" because the
# outputs (vm_id, vm_name) become known-after-apply.
if VM in `terraform state list`:
    terraform apply -refresh-only -auto-approve   # drop from state a VM deleted by hand
state = terraform show -json

vm_in_state  = "proxmox_virtual_environment_vm.app" in state
gen_in_state = terraform_data.generation.output   (None on a brand-new state)

if vm_in_state:            generation = gen_in_state          # live VM: keep its number
elif gen_in_state:         generation = gen_in_state + 1      # VM gone, memory kept: bump
else:                      generation = seed                  # first ever run; seed = <ENV>_VM_GENERATION_SEED, default 1

write TF_VAR_vm_generation=<generation> to the job environment (dotenv or export)
```

`<ENV>_VM_GENERATION_SEED` exists so that, if a hand-made `serv-nath-nsft-prod-01` already exists when CI takes over, you set the seed to `2` and the first CI VM is `-02`.

Class sketch (`deploy/infra/generation.py`):

```python
@dataclass(frozen=True)
class StateSnapshot:
    vm_present: bool
    generation: int | None

    @classmethod
    def from_terraform_show(cls, show_json: dict) -> "StateSnapshot": ...

class GenerationResolver:
    def __init__(self, snapshot: StateSnapshot, seed: int = 1) -> None: ...
    def next(self) -> int: ...
```

Straightforward to unit-test with three snapshots (live / gone / empty).

### Scenarios

| Event | Name |
|---|---|
| First pipeline | `serv-nath-nsft-prod-01` |
| 50 more pipelines, VM untouched | still `-01` (plan: no changes) |
| `destroy_<env>_vm`, then next pipeline | `-02` |
| VM deleted by hand in Proxmox, next pipeline | refresh-only drops it, next is `-03` |
| Someone renames the VM in Proxmox UI | plan shows an in-place `name` update back to `-03`; guard allows `update` |

Proxmox VM names must be DNS-label-like (letters, digits, hyphens, ≤ 63 chars): `serv-nath-nsft-prod-01` is 22 characters and valid.

## Safety rails in CI

`prevent_destroy = true` is tempting but it also blocks the manual destroy job. Instead the pipeline uses a **plan guard**:

```bash
terraform plan -input=false -out=tfplan -detailed-exitcode   # 0 = no change, 2 = changes, 1 = error
terraform show -json tfplan > tfplan.json
python3 deploy/infra_deploy.py guard-plan --plan-json tfplan.json
terraform apply -input=false -auto-approve tfplan
```

`TerraformPlanGuard` (in `deploy/infra/plan_guard.py`) walks `resource_changes[].change.actions` and fails the job if any action is `delete` (which includes replace = `["delete","create"]` or `["create","delete"]`). It prints the offending resource and a hint: "run destroy_<env>_vm if this is intended".

In practice the guard is a small class:

```python
class TerraformPlanGuard:
    FORBIDDEN = {"delete"}

    def __init__(self, plan: dict, allowed: set[str]) -> None: ...
    def violations(self) -> list[PlanViolation]: ...   # resource address + actions
    def assert_safe(self) -> None: ...                 # raises PlanGuardError
```

## Import of an already existing prod VM

If a prod VM already exists (created by hand from the new template) and you want Terraform to adopt it instead of creating a second one:

```bash
cd deploy/terraform/prod
terraform init  # with TF_HTTP_* pointing to state prod-vm
export TF_VAR_vm_generation=1          # or whatever number the hand-made VM should carry
terraform import proxmox_virtual_environment_vm.app <node_name>/<vmid>
terraform apply -target=terraform_data.generation   # seed the counter in state
terraform plan  # expect a `name` update to serv-nath-nsft-prod-01 plus cloud-init / description / tag diffs; adjust HCL until clean
```

Do this once from your workstation; after that CI runs are no-ops. Alternatively keep the hand-made VM out of Terraform and let CI create a new one on a new IP — cleaner, since the hand-made VM was re-IP'd by hand and its address may fall outside the CI pool.

## Local development loop (laptop, before CI)

This is **not** a GitLab job. It is you, on your workstation, running the same Terraform files GitLab will run later, against a **throwaway** VM. Goal: prove clone + cloud-init + SSH work, without touching the real prod VM or the real prod Terraform state.

Two things to keep separate:

| | Real prod (CI only) | Sandbox (your laptop) |
|---|---|---|
| GitLab Terraform state name | `prod-vm` | `prod-vm-sandbox` |
| VM name | `serv-nath-nsft-prod-01` | `serv-nath-nsft-sandbox-01` |
| IP | whatever Pi-hole allocated in `.124–.200` | a free IP you pick by hand, e.g. `.190` |
| Folder | `deploy/terraform/prod/` | same files. `TF_VAR_env=sandbox` only changes the VM name |

Each environment CI deploys has its own root (`deploy/terraform/integration`, `validation`, `prod`) so RAM, disk and cores can differ. This dry run uses the prod root and a sandbox state name. `TF_VAR_env=sandbox` makes the VM name `…-sandbox-01` instead of `…-prod-01`.

### 1. Talk to Proxmox

Terraform needs the Proxmox API the same way CI will. The `bpg/proxmox` provider reads these env vars; they never go in the `.tf` files.

```bash
export PROXMOX_VE_ENDPOINT="https://<your-proxmox-hostname>:8006/"
# Single quotes: Proxmox token IDs contain "!" (terraform@pve!ci=…). In zsh, "!" inside
# double quotes triggers history expansion and yields: zsh: event not found: ci=…
export PROXMOX_VE_API_TOKEN='terraform@pve!ci=<the-uuid-from-pveum>'
export PROXMOX_VE_INSECURE=true   # only if the Proxmox cert is self-signed
```

Replace `<your-proxmox-hostname>` with the real name or IP you use in the browser (the `pve` in the original snippet was a placeholder). Paste the real secret from `pveum user token add` in place of `<the-uuid-from-pveum>` (keep the `terraform@pve!ci=` prefix exactly as Proxmox printed it).

### 2. Store state in GitLab, but under a sandbox name

Terraform must remember "I already created VM 123". That memory is the **state file**. We store it in GitLab (Operate → Terraform states), not on your disk, so CI and your laptop share the same mechanism.

```bash
export TF_STATE_NAME=prod-vm-sandbox
export TF_HTTP_ADDRESS="${GITLAB_URL}/api/v4/projects/${PROJECT_ID}/terraform/state/${TF_STATE_NAME}"
export TF_HTTP_LOCK_ADDRESS="${TF_HTTP_ADDRESS}/lock"
export TF_HTTP_UNLOCK_ADDRESS="${TF_HTTP_ADDRESS}/lock"
export TF_HTTP_LOCK_METHOD=POST
export TF_HTTP_UNLOCK_METHOD=DELETE
export TF_HTTP_USERNAME="<your-gitlab-username>"
export TF_HTTP_PASSWORD="<a-personal-access-token-with-api-scope>"
export TF_HTTP_RETRY_WAIT_MIN=5
# Self-hosted GitLab with a private CA (skip if your Mac already trusts the cert):
export TF_HTTP_CLIENT_CA_CERTIFICATE_PEM="$(cat /path/to/homelab-ca.pem)"
```

`GITLAB_URL` is your GitLab origin (e.g. `https://gitlab.example.com`). `PROJECT_ID` is the numeric id of this repo (Project overview → the number under the name, or Settings → General).

`TF_STATE_NAME=prod-vm-sandbox` is the important bit: it is a **different file** from `prod-vm`. Destroying the sandbox VM cannot delete the real prod state.

On your laptop you use a Personal Access Token because there is no `CI_JOB_TOKEN`. In CI, GitLab fills the same `TF_HTTP_*` vars automatically (see 04).

### 3. Tell Terraform what to build

Anything declared as `variable "foo"` in `variables.tf` can be set from the shell as `TF_VAR_foo`.

```bash
export TF_VAR_node_name=pve                    # Proxmox node that hosts VMs
export TF_VAR_template_vm_id=9000              # VMID of the Debian 13 cloud-init template
export TF_VAR_vm_ip=192.168.1.190              # throwaway IP, NOT a prod IP
export TF_VAR_env=sandbox                      # → name serv-nath-nsft-sandbox-01
export TF_VAR_vm_generation=1
export TF_VAR_fqdn=sandbox-test.nath-server.home   # required by variables.tf; Pi-hole record optional for a throwaway IP
```

`9000`, `pve` and `.190` are examples. Use your real node name, real template VMID, and an IP that nothing uses.

No SSH key variable: the clone inherits `nath` and the keys already stored on the template. On your laptop, SSH with the **private** key that matches that template public key (the gitlab-runner key, or your own if you added it to the template in Proxmox). To change who can log in, edit the template's Cloud-Init SSH keys in the Proxmox UI — do not pass keys through Terraform.

### 4. Plan, then apply (Docker on your laptop)

Run this on **your Mac**, from the **repository root**, in the **same shell** where you exported §1–§3. You do not need a local `terraform` binary; use the same image as CI (`hashicorp/terraform:1.16`). Docker Desktop must be running.

Provider plugins and `.terraform/` are written under `deploy/terraform/prod/` on your disk (bind-mounted into the container).

```bash
cd ~/Desktop/budget-manager   # your clone path

# Shorthand — every terraform subcommand below uses the same env forwarding.
tf() {
  docker run --rm -it \
    -v "$PWD/deploy/terraform/prod:/workspace" \
    -w /workspace \
    -e PROXMOX_VE_ENDPOINT -e PROXMOX_VE_API_TOKEN -e PROXMOX_VE_INSECURE \
    -e TF_HTTP_ADDRESS -e TF_HTTP_LOCK_ADDRESS -e TF_HTTP_UNLOCK_ADDRESS \
    -e TF_HTTP_LOCK_METHOD -e TF_HTTP_UNLOCK_METHOD -e TF_HTTP_RETRY_WAIT_MIN \
    -e TF_HTTP_USERNAME -e TF_HTTP_PASSWORD \
    -e TF_HTTP_CLIENT_CA_CERTIFICATE_PEM \
    -e TF_VAR_node_name -e TF_VAR_template_vm_id -e TF_VAR_vm_ip -e TF_VAR_env \
    -e TF_VAR_vm_generation -e TF_VAR_fqdn \
    hashicorp/terraform:1.16 "$@"
}

tf init -reconfigure
# If GitLab TLS still fails and you accept the risk for sandbox only:
# tf init -reconfigure -backend-config=skip_cert_verification=true

tf plan          # print what would happen; creates nothing
```

Read the plan. You should see **one VM to create**, named `serv-nath-nsft-sandbox-01`, IP `192.168.1.190`. If the plan mentions the real prod VM, stop: the state name or `TF_VAR_env` is wrong.

When the plan looks right:

```bash
tf apply         # type yes when prompted; Proxmox clones the template
ssh Nath@192.168.1.190   # on the Mac, not inside Docker; key must match the template
tf plan          # should now say "No changes"
```

To throw the experiment away without resetting the generation counter:

```bash
tf destroy -target=proxmox_virtual_environment_vm.app
```

That removes the sandbox VM in Proxmox. The `prod-vm-sandbox` state file stays in GitLab (with the generation memory). You can delete that state file later in the GitLab UI if you want a clean slate.

## Known provider gotchas

- After the first sandbox clone, check `qm config <vmid> | grep -E 'sshkeys|ciuser'`. Those must still match the template. If the provider cleared them because `initialization` was set, we have a problem: do **not** "fix" it by adding `user_account` in Terraform. File it as a provider issue and, if needed, set `lifecycle.ignore_changes` on the parts of `initialization` that Proxmox inherited (or pin a provider version that preserves unset cloud-init fields).
- If `initialization` seems ignored after clone, check `initialization.interface` matches the template's cloud-init slot (`sata1` on d13t; run `qm config <template-vmid> | grep cloudinit`) and that the datastore allows the `cloudinit` content type.
- Changing `cpu`/`memory` on a cloned VM has in some provider versions dropped the cloud-init `ipconfig0`. Mitigation: keep `ip_config` explicit in HCL (we do), and after any hardware change verify `qm config <vmid> | grep ipconfig0`.
- `agent.enabled = true` while the guest agent is not running makes every refresh/apply wait for the agent timeout. Confirm the agent is running in the template before enabling.
