
# Creates disk with count
resource "google_compute_disk" "default" {
  count                     = var.disk_count * var.vm_count
  name                      = "disk-${var.disk_type}-${var.disk_zone}-${var.run_label}-${count.index}"
  type                      = var.disk_type
  zone                      = var.disk_zone
  size                      = var.disk_size
  labels = {
    Name = var.run_label
  }
}

# Attaches disks to the instance
resource "google_compute_attached_disk" "default" {
  count    = var.disk_count * var.vm_count
  disk     = google_compute_disk.default[count.index].id
  instance = google_compute_instance.test[count.index % var.vm_count].id
}
