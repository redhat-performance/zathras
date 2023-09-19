
resource "google_compute_network" "test-network" {
  count                   = var.network_count
  name                    = "${var.run_label}-${var.project_id}-${var.machine_type}-${count.index}"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "test-subnet" {
  count         = var.network_count
  name          = "${var.run_label}-${var.project_id}-${var.machine_type}-${count.index}"
  ip_cidr_range = "10.20.3${count.index}.0/24"
  network       = google_compute_network.test-network[count.index].id
}

resource "google_compute_firewall" "uperf-ingress" {
  count   = var.network_count
  name    = "${var.run_label}-${var.project_id}-${var.machine_type}-${count.index}"
  network = google_compute_network.test-network[count.index].id

  # Allow all communication 0.0.0.0/0 on the specific network  
  allow {
    protocol = "all"
  }
}
