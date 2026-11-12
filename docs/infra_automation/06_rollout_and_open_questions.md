# 06 — Rollout plan, testing, rollback, security, open questions

## Rollout in six steps

Each step ends in a verifiable state and can be stopped without breaking the current manual process.

### Step 0 — Homelab prerequisites (manual, ~30 min)

- [x] Proxmox: `terraform@pve` user, role, API token (02 §1)
- [x] Proxmox: confirm template facts — VMID **121**, node **nath-server**, datastore **local-lvm**, cloud-init **sata1** (no size — normal), OS disk **sata0** 16G, `agent: 1`, `ipconfig0` `.108/24`, `ciuser: Nath`, gitlab-runner key in `sshkeys`
- [x] Pi-hole: generate an *application password* for CI; confirm version (v6 API present at `http://192.168.1.105/api/info/version`)
- [x] Network: confirm `.124–.200` is outside every DHCP range
- [x] GitLab: add the CI variables listed in 04; mark `master` protected
- [x] Runner: confirm it can reach `<pve>:8006`, `192.168.1.105:80`, and ping the pool

### Step 1 — Terraform from the workstation, sandbox state

- Write `deploy/terraform/prod/*.tf` (02). Integration and validation are separate roots with the same resources.
- `TF_STATE_NAME=prod-vm-sandbox`, `TF_VAR_vm_ip=192.168.1.199`, `TF_VAR_env=sandbox`, `TF_VAR_vm_generation=1`.
- `terraform apply` → a VM `serv-nath-nsft-sandbox-01` boots directly on `.199`, `ssh nath@192.168.1.199` works with the runner key, `sudo -n true` works.
- `terraform plan` again → **no changes** (fix `ignore_changes` until it is clean).
- `terraform destroy -target=proxmox_virtual_environment_vm.app`, then apply again with `TF_VAR_vm_generation=2` → `serv-nath-nsft-sandbox-02`.

Exit criterion: create → plan clean → targeted destroy → recreate with the next number, without touching the Proxmox UI.

### Step 2 — Pi-hole client + allocator

- Write `deploy/infra/` and `deploy/infra_deploy.py` (03).
- Unit tests with a fake client.
- Manual run against the real Pi-hole with `--fqdn sandbox.nath-server.home`: expect `.124` (or the first free one), the record appears in the Pi-hole UI, a second run reuses it, `release-ip` removes it.

### Step 3 — Ansible on a sandbox VM

- Apply 05 changes (`nath` + become). Inventory stays the FQDN.
- For a sandbox VM that is not yet in Pi-hole, add a temporary `sandbox.nath-server.home` record (or a throwaway inventory line) and run `ansible_deploy.py --env prod ...`. Expect the full stack up on that hostname.
- This validates the non-root path before touching CI.

### Step 4 — CI on a branch, sandbox names

- Add the `infra` stage to `.gitlab-ci.yml` but temporarily set `TF_STATE_NAME=prod-vm-sandbox`, `PROD_VM_FQDN=sandbox.nath-server.home`, `TF_VAR_env=sandbox` via branch-scoped variables or a `-sandbox` suffix variable.
- Push → pipeline creates the sandbox VM end-to-end, then `update_prod` deploys onto it.
- Rerun the pipeline → `allocate_prod_ip` says `REUSED=true`, `setup_prod_vm` plan exit code 0, `update_prod` redeploys.
- Run `destroy_prod_vm` manually → VM and record gone.

### Step 5 — Switch to real prod

Two possible paths:

- **A. New VM (recommended).** Keep the current hand-made prod running. Merge with real names (`prod-vm`, `nsft.nath-server.home`). Because the record `nsft.nath-server.home` already exists in Pi-hole pointing at the old VM, the allocator will *reuse that IP* and Terraform would create a second VM on the same IP → conflict. So first: rename the old record (e.g. `nsft-old.nath-server.home`), then run the pipeline. New VM gets `.124`, DNS flips, Ansible deploys. Migrate the Postgres data (`pg_dump` on old → restore on new, or copy the backup dir) before flipping if you need continuity. Delete the old VM when satisfied.
- **B. Adopt the existing VM.** `terraform import` (02) plus create the Pi-hole record if missing. Faster but keeps a VM whose IP was chosen by hand and may sit outside the CI pool.

### Step 6 — Cleanup

- Remove sandbox state in GitLab (Operate → Terraform states → delete `prod-vm-sandbox`).
- Update the README "Deployment" section to point at `docs/infra_automation/`.

### Step 7 — Integration and validation environments

Done in the repo (same jobs stamped per environment, see 04). To switch them on:

- Pi-hole: nothing to do; records `nsft.integration.nath-server.home` and `nsft.validation.nath-server.home` are created by `allocate_<env>_ip`.
- GitLab: add the `INTEGRATION_*` and `VALIDATION_*` variables (04). `INTEGRATION_*` and the shared Proxmox/Pi-hole variables must be **unprotected** because integration runs on every branch.
- Proxmox: capacity for up to three VMs of the default size (2 vCPU, 1 GiB, 16 GiB) at the same time.
- First master pipeline: integration VM `-01` is created, tested and destroyed; validation VM `-01` is created and deployed; prod infra converges; `update_prod` waits for a click.
- Every later pipeline on a branch costs one integration VM create/destroy cycle (~5–10 min); set `INTEGRATION_KEEP_VM=true` temporarily to debug on the VM.

## Rollback

- Infra jobs are additive. Deleting the `infra` stage and restoring `SSH_HOST: nsft.nath-server.home` + `remote_user: root` (if root is still possible) returns to today's flow.
- A VM created by Terraform can be handed back to manual management with `terraform state rm proxmox_virtual_environment_vm.app`; the VM keeps running.
- Pi-hole records are plain text lines; the UI shows and removes them.

## Security notes

1. **The `nath` password.** It was pasted in chat and is baked into the template. Do not write it into the repo or these docs. If passwordless sudo works, CI never needs it. Rotate it after the pipeline is validated (`passwd` in the template, re-convert), or better: disable password authentication in the template (`PasswordAuthentication no` in sshd; cloud-init `ssh_pwauth: false`) and rely on keys only. The Proxmox console still works for emergencies.
2. **Proxmox token** has VM-level rights on `/`. Scope it to a pool (`/pool/ci`) if you want to limit blast radius: `pveum aclmod /pool/ci ...` and create the VM with `pool_id = "ci"`.
3. **Pi-hole application password** can change every `dns.hosts` entry. Acceptable in a homelab; there is no finer-grained role in Pi-hole.
4. **Protected variables + protected branch** so a feature branch cannot touch prod infra.
5. `terraform show -json` output contains no secrets here (no passwords in HCL), so keeping `tfplan.json` as an artifact is fine.

## Cost of a no-op pipeline run

| Job | Typical duration |
|---|---|
| `allocate_prod_ip` | ~10 s |
| `setup_prod_vm` (no change) | ~40 s (image pull, init, plan, wait-ssh instant) |
| `destroy_prod_vm` | manual only |

## Open questions for you

Answering these lets the implementation start without guesswork. Defaults I would take are in *italics*.

**Proxmox**
1. Proxmox VE version (8.x or 9.x)? Single node or cluster? Node name? *single node `pve`*
2. VMID of the Debian 13 cloud-init template, and the datastore its disks live on? *`local-lvm`*
3. Is the `.108` static IP set in the Proxmox cloud-init tab (`ipconfig0`) or written inside the image? (Decides whether cloud-init can override it — the whole design assumes it can.)
4. Cloud-init drive interface (`sata1` on d13t), OS disk interface (`scsi0`?), and is `qemu-guest-agent` installed and enabled in the template?
5. Was `cloud-init clean` run before converting to template? Is `nath` created by cloud-init (`ciuser`) or baked into the image? Does `nath` have `NOPASSWD` sudo?
6. Desired VM sizing for prod: cores / RAM / disk? *2 vCPU, 4 GB, 40 GB*
7. Should the prod VM have a fixed VMID (e.g. `200`) for readability? *let Proxmox choose*

**Network / DNS**
8. Pi-hole version — v6 (new REST API) or v5? *v6*
9. Who serves DHCP (router or Pi-hole), and what is its range? `.124–.200` must be outside it.
10. Is anything statically configured in `.124–.200` that Pi-hole does not know about? (`d13t` `.108` and `anytype` `.114` are below the pool.) Silent hosts that do not answer ping would need to go in `PROD_IP_RESERVED`.
11. Does the GitLab runner host reach Proxmox `:8006` and Pi-hole `:80` directly, and can its Docker containers ping the LAN?
12. HTTPS: `update_prod` declares `https://nsft.nath-server.local` as environment URL but nginx serves plain HTTP on 80. Is there a reverse proxy in front (and should the automation register the VM there too)?

**GitLab**
13. Self-managed GitLab version? (Terraform state backend needs the Infrastructure → Terraform feature enabled; it is on by default.)
14. Is `master` a protected branch, and can you add protected/masked variables at project level?
15. Preference: run infra jobs on every `master` pipeline (*default*), or only when `deploy/terraform/**` changes / manually?

**Process**
16. For the switch to real prod: new VM + data migration (*recommended*) or import the existing VM?
17. ~~Do you also want `demo`/`test` VMs managed the same way now, or prod only first?~~ Decided: `test`/`demo` were renamed `integration`/`validation` and are managed the same way (Step 7, 04). Integration is disposable and runs the Flask pytest suite; validation is the pre-production gate before the manual `update_prod`.
