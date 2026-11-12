# Terraform root: prod VM

Clones the Debian 13 cloud-init template into `serv-nath-nsft-prod-NN`.
GitLab state name: `prod-vm`.

Sizing for this environment only is the defaults in `variables.tf`
(`memory_mb`, `cores`, `os_disk_size_gb`, ...). Integration and validation
have their own copies of this root.

CI sets `TF_ROOT=deploy/terraform/prod`. A local sandbox run can still use
this directory with another state name (`prod-vm-sandbox`) and `TF_VAR_env=sandbox`.
See `docs/infra_automation/02_terraform_proxmox.md`.
