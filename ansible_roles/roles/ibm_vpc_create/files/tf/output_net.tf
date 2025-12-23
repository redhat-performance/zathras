# Output for the instance ID
output "instance_id0" {
  value = ibm_is_instance.instance[0].id
  description = "The ID of the first instance"
}

# Output for the instance name
output "instance_name0" {
  value = ibm_is_instance.instance[0].name
  description = "The name of the first instance"
}

# Output for the second instance ID (if exists)
output "instance_id1" {
  value = var.vm_count > 1 ? ibm_is_instance.instance[1].id : "none"
  description = "The ID of the second instance"
}

# Output for the second instance name (if exists)
output "instance_name1" {
  value = var.vm_count > 1 ? ibm_is_instance.instance[1].name : "none"
  description = "The name of the second instance"
}

# Output for the public IP - using floating IP
resource "ibm_is_floating_ip" "floating_ip" {
  count          = var.vm_count
  name           = "${var.run_label}-fip-${format("%02d", count.index)}"
  target         = ibm_is_instance.instance[count.index].primary_network_interface[0].id
  resource_group = data.ibm_resource_group.resource_group.id
}

output "public_ip0" {
  value = ibm_is_floating_ip.floating_ip[0].address
  description = "The public IP of the first instance"
}

output "public_ip1" {
  value = var.vm_count > 1 ? ibm_is_floating_ip.floating_ip[1].address : "none"
  description = "The public IP of the second instance"
}

# Output for the private IP
output "private_ip0" {
  value = ibm_is_instance.instance[0].primary_network_interface[0].primary_ipv4_address
  description = "The private IP of the first instance"
}

output "private_ip1" {
  value = var.vm_count > 1 ? ibm_is_instance.instance[1].primary_network_interface[0].primary_ipv4_address : "none"
  description = "The private IP of the second instance"
}

# Output for the secondary private IP (if using network interface)
output "secondary_ip0" {
  value = var.network_count > 0 ? ibm_is_instance_network_interface.secondary_interface[0].primary_ipv4_address : "none"
  description = "The secondary private IP of the first instance"
}

output "secondary_ip1" {
  value = var.vm_count > 1 && var.network_count > 0 ? ibm_is_instance_network_interface.secondary_interface[1].primary_ipv4_address : "none"
  description = "The secondary private IP of the second instance"
}