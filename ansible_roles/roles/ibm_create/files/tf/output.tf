output "instance_id" {
  description = "IDs of the created instances"
  value       = ibm_is_instance.test[*].id
}

output "instance_name" {
  description = "Names of the created instances"
  value       = ibm_is_instance.test[*].name
}

output "public_ip" {
  description = "Public IP addresses (floating IPs)"
  value       = ibm_is_floating_ip.zathras_floating_ip[*].address
}

output "private_ip" {
  description = "Private IP addresses"
  value       = ibm_is_instance.test[*].primary_network_interface[0].primary_ipv4_address
}

output "vpc_id" {
  description = "VPC ID"
  value       = local.vpc_id
}

output "subnet_id" {
  description = "Subnet ID"
  value       = ibm_is_subnet.zathras_subnet.id
}

output "zone" {
  description = "Zone where instances are created"
  value       = var.zone
}
