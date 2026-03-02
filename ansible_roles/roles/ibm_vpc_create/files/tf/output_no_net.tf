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

# Output for the private IP
output "private_ip0" {
  value = ibm_is_instance.instance[0].primary_network_interface[0].primary_ipv4_address
  description = "The private IP of the first instance"
}