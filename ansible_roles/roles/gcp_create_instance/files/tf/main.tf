
locals {
  is_preemptible = var.vm_type == "preemptible" ? true : false
}

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "3.5.0"
    }
  }
}

# Defines default values for the provider
provider "google" {

  project = var.project_id
  region  = var.region
}

# Defines a VM
resource "google_compute_instance" "test" {
  count                     = var.vm_count
  name                      = "${var.run_label}-${var.project_id}-${var.machine_type}-${count.index}"
  machine_type              = var.machine_type
  allow_stopping_for_update = "true"
  zone                      = var.zone
  labels = {
    Name = var.run_label
  }

  boot_disk {
    initialize_params {
      image = var.vm_image
    }
  }

  scheduling {
    preemptible       = local.is_preemptible
    automatic_restart = !local.is_preemptible
  }

  network_interface {
    network = "default"
    # Following access_config block creates a public IP.
    # (Optional)Edit here if you need to assign a static IP.
    access_config {
    }
  }

  # Dynamically create multiple network interface
  dynamic "network_interface" {
    for_each = range(var.network_count)

    content {
      # Links to the subnet, check network.tf for details
      subnetwork = google_compute_subnetwork.test-subnet[network_interface.value].id
    }
  }

  # This is required when you're attaching disk later.
  lifecycle {
    ignore_changes = [attached_disk]
  }

  # copies ssh public key into the system for ssh access to the VM
  metadata = {
    ssh-keys = "${var.test_user}:${file(var.ssh_key_path)}"
  }

  # Ensures that instance is created after successful creation of networks
  depends_on = [
    google_compute_subnetwork.test-subnet,
    google_compute_firewall.uperf-ingress
  ]
}
