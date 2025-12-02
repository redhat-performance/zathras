# Create regular data volumes
resource "ibm_is_volume" "data_volume" {
  count          = var.vm_count * var.disk_count
  name           = "${var.run_label}-volume-${format("%02d", count.index)}"
  profile        = var.disk_profile
  zone           = var.zone
  capacity       = var.disk_size
  resource_group = data.ibm_resource_group.resource_group.id
  tags           = local.tags
}

# Attach volumes to instances
resource "ibm_is_instance_volume_attachment" "volume_attachment" {
  count    = var.vm_count * var.disk_count
  instance = element(
    ibm_is_instance.instance.*.id,
    floor(count.index / var.disk_count)
  )
  volume = element(
    ibm_is_volume.data_volume.*.id,
    count.index
  )
  name     = "${var.run_label}-attachment-${format("%02d", count.index)}"
  delete_volume_on_instance_delete = false
}