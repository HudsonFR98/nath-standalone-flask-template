output "vm_id" {
  description = "Proxmox VMID of the environment's VM."
  value       = proxmox_virtual_environment_vm.app.vm_id
}

output "vm_name" {
  description = "Name of the VM (serv-nath-<app>-<env>-NN)."
  value       = proxmox_virtual_environment_vm.app.name
}

output "env" {
  description = "Environment this state belongs to."
  value       = var.env
}

output "vm_ip" {
  description = "Static IPv4 address configured through cloud-init."
  value       = var.vm_ip
}

output "fqdn" {
  description = "FQDN registered in Pi-hole."
  value       = var.fqdn
}

output "generation" {
  description = "Generation number stored in state."
  value       = terraform_data.generation.output
}
