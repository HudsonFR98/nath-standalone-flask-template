terraform {
  required_version = ">= 1.6"

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.114"
    }
  }

  # GitLab-managed Terraform state. All connection details are injected
  # through TF_HTTP_* environment variables by the CI job (see .gitlab-ci.yml),
  # so nothing sensitive lives in this file.
  backend "http" {}
}

# Credentials are read from the environment:
#   PROXMOX_VE_ENDPOINT   https://<proxmox-host>:8006/
#   PROXMOX_VE_API_TOKEN  terraform@pve!ci=<secret>
#   PROXMOX_VE_INSECURE   true (self-signed certificate on the homelab)
provider "proxmox" {}
