# returns the IP address of the vm we created to output
output "public_ip_list" {
 value = google_compute_instance.test[*].network_interface.0.access_config.0.nat_ip
}

output "internal_ip_list" {
  value = google_compute_instance.test[*].network_interface[*].network_ip
}