# Terraform root: validation VM

Clones the Debian 13 cloud-init template into `serv-nath-nsft-validation-NN`.
GitLab state name: `validation-vm`.

Sizing for this environment only is the defaults in `variables.tf`
(`memory_mb`, `cores`, `os_disk_size_gb`, ...). Integration and prod have
their own copies of this root.

CI sets `TF_ROOT=deploy/terraform/validation`. See `docs/infra_automation/`.
