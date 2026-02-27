# This file handles additional network configurations for IBM Cloud

# Firewall rules for private network traffic (if additional networks are configured)
resource "ibm_is_security_group_rule" "private_network_inbound" {
  count     = var.network_count > 0 ? 1 : 0
  group     = ibm_is_security_group.zathras_sg.id
  direction = "inbound"
  remote    = "10.0.0.0/8"
}

resource "ibm_is_security_group_rule" "private_network_outbound" {
  count     = var.network_count > 0 ? 1 : 0
  group     = ibm_is_security_group.zathras_sg.id
  direction = "outbound"
  remote    = "10.0.0.0/8"
}
