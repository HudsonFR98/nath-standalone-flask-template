locals {
  vm_name = format("serv-nath-%s-%s-%02d", var.app_short, var.env, var.vm_generation)
}

# Generation counter kept in state. `infra_deploy.py next-generation` reads it
# back from `terraform show -json` and bumps it when the VM resource is gone,
# so the value survives a `terraform destroy -target=proxmox_virtual_environment_vm.app`.
resource "terraform_data" "generation" {
  input = var.vm_generation
}

resource "proxmox_virtual_environment_vm" "app" {
  name        = local.vm_name
  description = "Managed by Terraform (GitLab CI). FQDN: ${var.fqdn}"
  node_name   = var.node_name
  tags        = []

  on_boot = true
  started = true

  clone {
    vm_id = var.template_vm_id
    full  = true
  }

  agent {
    enabled = true
  }

  cpu {
    cores = var.cores
    type  = "host"
  }

  memory {
    dedicated = var.memory_mb
    floating  = var.memory_balloon_enabled ? var.memory_balloon_min_mb : 0
  }

  disk {
    datastore_id = var.datastore_id
    interface    = var.os_disk_interface
    size         = var.os_disk_size_gb
    discard      = "on"
  }

  initialization {
    datastore_id = var.datastore_id
    interface    = var.cloudinit_interface

    ip_config {
      ipv4 {
        address = "${var.vm_ip}/${var.cidr_prefix}"
        gateway = var.gateway
      }
    }

    dns {
      domain  = var.dns_domain
      servers = var.dns_servers
    }

    # No user_account block on purpose: the user `Nath`, its password and the
    # gitlab-runner SSH key are baked into the template's cloud-init config.
  }

  lifecycle {
    # `clone` only matters at creation; tags are re-sorted by Proxmox.
    ignore_changes = [clone, tags]
    # Destruction is allowed here (destroy_<env>_vm jobs); the CI plan guard
    # (`infra_deploy.py guard-plan`) is what blocks delete/replace on apply.
  }
}
