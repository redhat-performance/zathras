# returns the IP address of the vm we created to output
output "public_ip_address" {
 value = data.azurerm_public_ip.publicip[*].ip_address
}
