# Create secondary network interface
resource "ibm_is_instance_network_interface" "secondary_interface" {
  count          = var.vm_count
  instance       = element(ibm_is_instance.instance.*.id, count.index)
  name           = "${var.run_label}-nic-private-${format("%02d", count.index)}"
  subnet         = ibm_is_subnet.private_subnet.id
  security_groups = [ibm_is_security_group.security_group.id]
}