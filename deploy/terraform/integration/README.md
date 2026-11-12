# Terraform root: integration VM

Clones the Debian 13 cloud-init template into `serv-nath-nsft-integration-NN`.
GitLab state name: `integration-vm`.

Sizing for this environment only is the defaults in `variables.tf`
(`memory_mb`, `cores`, `os_disk_size_gb`, ...). Validation and prod have
their own copies of this root.

CI sets `TF_ROOT=deploy/terraform/integration`. See `docs/infra_automation/`.
