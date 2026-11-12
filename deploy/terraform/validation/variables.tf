# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

variable "app_short" {
  description = "Short application code used in the VM name (e.g. nsft)."
  type        = string
  default     = "nsft"
}

variable "env" {
  description = <<-EOT
    Environment name used in the VM name (serv-nath-<app_short>-<env>-NN).
    This root is validation. CI sets TF_VAR_env=validation. Override only for a local
    sandbox run that uses a different GitLab state name than `validation-vm`.
  EOT
  type        = string
  default     = "validation"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*$", var.env))
    error_message = "env must be lower-case letters, digits or hyphens (e.g. integration, validation, prod)."
  }
}

variable "vm_generation" {
  description = <<-EOT
    Sequential generation number of the VM. Incremented by `infra_deploy.py
    next-generation` every time the previous VM was destroyed, so that a
    recreated VM gets a fresh name (serv-nath-nsft-<env>-01, -02, ...).
  EOT
  type        = number

  validation {
    condition     = var.vm_generation >= 1 && var.vm_generation == floor(var.vm_generation)
    error_message = "vm_generation must be a positive integer."
  }
}

# ---------------------------------------------------------------------------
# Proxmox placement
# ---------------------------------------------------------------------------

variable "node_name" {
  description = "Proxmox node hosting the VM."
  type        = string
}

variable "template_vm_id" {
  description = "VMID of the Debian 13 cloud-init template to clone."
  type        = number
}

variable "datastore_id" {
  description = "Datastore that receives the OS disk and the cloud-init drive."
  type        = string
  default     = "local-lvm"
}

# ---------------------------------------------------------------------------
# Sizing — this root only (validation). The other environments have their own copy.
# ---------------------------------------------------------------------------

variable "cores" {
  description = "Number of vCPU cores."
  type        = number
  default     = 2
}

variable "memory_mb" {
  description = "Maximum memory (Proxmox “Memory”, provider `memory.dedicated`) in MiB."
  type        = number
  default     = 1024
}

variable "memory_balloon_enabled" {
  description = "When true, Proxmox installs the virtio balloon device (`memory.floating` > 0)."
  type        = bool
  default     = true
}

variable "memory_balloon_min_mb" {
  description = <<-EOT
    Minimum guaranteed memory (Proxmox “Minimum memory”, provider `memory.floating`) in MiB.
    Must be <= memory_mb. When lower than memory_mb, the host may reclaim RAM down to this floor
    under pressure (QEMU guest agent should stay enabled). When equal to memory_mb, the balloon
    device is present but there is no reclaim range (same as a fresh PVE GUI VM).
  EOT
  type        = number
  default     = 512

  validation {
    condition = var.memory_balloon_min_mb >= 32 && (
      !var.memory_balloon_enabled || var.memory_balloon_min_mb <= var.memory_mb
    )
    error_message = "memory_balloon_min_mb must be >= 32 and cannot exceed memory_mb when ballooning is enabled."
  }
}

variable "os_disk_size_gb" {
  description = "OS disk size in GiB. Must be >= the template disk size (16)."
  type        = number
  default     = 16
}

variable "os_disk_interface" {
  description = "Interface of the OS disk as declared on the template."
  type        = string
  default     = "sata0"
}

variable "cloudinit_interface" {
  description = "Interface of the cloud-init drive as declared on the template."
  type        = string
  default     = "sata1"
}

# ---------------------------------------------------------------------------
# Networking (address comes from the Pi-hole allocation step)
# ---------------------------------------------------------------------------

variable "vm_ip" {
  description = "Static IPv4 address allocated by `infra_deploy.py allocate-ip`."
  type        = string

  validation {
    condition     = can(cidrnetmask("${var.vm_ip}/32"))
    error_message = "vm_ip must be a valid IPv4 address."
  }
}

variable "cidr_prefix" {
  description = "Prefix length of the LAN."
  type        = number
  default     = 24
}

variable "gateway" {
  description = "Default gateway of the LAN."
  type        = string
  default     = "192.168.1.1"
}

variable "dns_servers" {
  description = "DNS servers pushed through cloud-init (Pi-hole first)."
  type        = list(string)
  default     = ["192.168.1.105"]
}

variable "dns_domain" {
  description = "DNS search domain pushed through cloud-init."
  type        = string
  default     = "nath-server.home"
}

variable "fqdn" {
  description = "FQDN registered in Pi-hole for this VM; stored in the VM description."
  type        = string
}
