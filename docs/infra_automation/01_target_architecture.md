# 01 — Target architecture

## Today (manual)

```text
Admin (you)                                   GitLab CI
─────────────────────────────────────────     ──────────────────────────────
1. Proxmox UI: clone Debian 13 template
2. VM boots on 192.168.1.108 (template default, DNS d13t.nath-server.home)
3. Pick a free IP by hand, change it on the VM
4. Pi-hole UI: add a new alias for it (e.g. nsft.nath-server.home → <ip>)
                                              5. build_docker
                                              6. update_prod (Ansible, as root)
```

Problems:

- Steps 1–4 are the only non-reproducible part of the deployment.
- Every clone starts on `.108` (`d13t.nath-server.home`), so two fresh clones cannot coexist until one is re-IP'd by hand.
- `update_prod` assumes `root` SSH, which the new cloud-init template no longer offers.

## Target (automated)

```text
GitLab CI (runner on the LAN)
──────────────────────────────────────────────────────────────────────────────
stage docker   build_docker       image → registry

stage infra    allocate_prod_ip   ──HTTP──▶ Pi-hole 192.168.1.105  (/api/config/dns/hosts)
                                            reuse "nsft.nath-server.home" if present
                                            else first free in .124–.200, PUT record
                                  ▼ dotenv: PROD_VM_IP, PROD_VM_FQDN

               setup_prod_vm      ──HTTPS─▶ Proxmox API :8006  (Terraform, bpg/proxmox)
                                            clone template VMID → VM "serv-nath-nsft-prod-01"
                                            cloud-init: ip=PROD_VM_IP/24 gw=.1 (user + SSH keys inherited from the template)
                                            state → GitLab Terraform state "prod-vm"
                                  ──SSH───▶ nath@PROD_VM_IP  cloud-init status --wait
                                  ▼ dotenv: PROD_VM_ID

stage prod     update_prod        ──SSH───▶ Nath@nsft.nath-server.home, sudo
                                            Ansible: docker, dirs, registry, files, containers, verify
```

### Components and who talks to whom

| From | To | Protocol / port | Credential |
|---|---|---|---|
| Runner job | Pi-hole `192.168.1.105` | HTTP `:80` (`/api/...`) | Pi-hole **application password** (CI var) |
| Runner job | Proxmox API | HTTPS `:8006` | Proxmox **API token** for a dedicated `terraform@pve` user (CI var) |
| Runner job | GitLab | HTTPS (`/api/v4/projects/:id/terraform/state/prod-vm`) | `CI_JOB_TOKEN` |
| Runner job | New VM | SSH `:22` as `Nath` | `/runner-ssh/id_rsa` (already mounted on the runner; public key already in the template) |
| New VM | GitLab registry / Dependency Proxy | HTTPS | handled by existing Ansible `registry` role |

### Network and DNS view

```text
192.168.1.0/24, gateway 192.168.1.1
├── .105  Pi-hole            DNS for every device/VM
├── .108  d13t.nath-server.home     template default IP — reserved for manual template boots, never used by the automated flow
├── .114  anytype.nath-server.home  existing VM, outside the pool
├── .124–.200  "CI-managed pool"  ← allocate_prod_ip picks here
│     └── .124 (first run)  serv-nath-nsft-prod-01  nsft.nath-server.home
└── <runner host>, <proxmox host>, ...
```

The pool must not overlap your router/Pi-hole DHCP range (see open questions). Today's known hosts (`d13t` at `.108`, `anytype` at `.114`) are below the pool and never considered. Should a host ever live inside the pool, it is skipped as long as it has a Pi-hole record or answers ping; add any silent ones to `PROD_IP_RESERVED`.

### Naming

| Thing | Value | Where it comes from |
|---|---|---|
| Proxmox VM name | `serv-nath-nsft-prod-01` | `serv-nath-<app_short>-<env>-<NN>`; `NN` is a generation counter kept in Terraform state, bumped each time the VM is removed and recreated (02 "VM naming") |
| Guest hostname | `nsft` | cloud-init (`hostname` in Terraform initialization) |
| FQDN / DNS record | `nsft.nath-server.home` | constant, same as `SSH_HOST` today |
| Terraform state name | `prod-vm` | one state per environment: `integration-vm`, `validation-vm`, `prod-vm` |
| Pi-hole record | `<ip> nsft.nath-server.home` | one line in `dns.hosts` |

### Idempotency contract

| Run | Pi-hole | Terraform | Ansible |
|---|---|---|---|
| First | record missing → allocate + PUT | state empty → clone VM | full deploy |
| Later (no change) | record found → reuse IP, no write | plan: no changes | redeploy containers |
| Template updated in Proxmox | record found | plan may propose **replace** → job **fails** by design (plan guard) | not reached |
| VM deleted by hand in Proxmox | record found | state refresh sees VM gone → plan: create | full deploy on same IP |
| Record deleted by hand in Pi-hole | allocates a new IP (could differ!) | plan: change `ip_config` → VM cloud-init updated, reboot needed | see 03 for how we pin the IP to avoid this |

### Environments beyond prod

Everything above is drawn for `prod`. Each environment has its own Terraform root (`deploy/terraform/<env>`) so sizing can differ, and the Python CLI (`infra_deploy.py --env`) is shared. State name, VM name, FQDN and dotenv prefix:

| env | VM | FQDN | state | dotenv prefix | lifecycle |
|---|---|---|---|---|---|
| `integration` | `serv-nath-nsft-integration-NN` | `nsft.integration.nath-server.home` | `integration-vm` | `INTEGRATION_` | created and destroyed by every pipeline (tests run in between) |
| `validation` | `serv-nath-nsft-validation-NN` | `nsft.validation.nath-server.home` | `validation-vm` | `VALIDATION_` | long-lived pre-production |
| `prod` | `serv-nath-nsft-prod-NN` | `nsft.nath-server.home` | `prod-vm` | `PROD_` | long-lived |

All three draw from the same Pi-hole pool `.124–.200`; a record is a reservation, so they never collide. Because the integration VM is recreated at each pipeline, its generation counter grows quickly — that is expected and harmless (the counter lives in `integration-vm` state only).
