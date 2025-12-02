# Create pbench volumes
resource "ibm_is_volume" "pbench_volume" {
  count          = var.vm_count * var.pb_disk_count
  name           = "${var.run_label}-pbench-volume-${format("%02d", count.index)}"
  profile        = var.pb_disk_profile
  zone           = var.zone
  capacity       = var.pb_vol_size
  resource_group = data.ibm_resource_group.resource_group.id
  tags           = local.tags
}

# Attach pbench volumes to instances
resource "ibm_is_instance_volume_attachment" "pbench_volume_attachment" {
  count    = var.vm_count * var.pb_disk_count
  instance = element(
    ibm_is_instance.instance.*.id,
    floor(count.index / var.pb_disk_count)
  )
  volume = element(
    ibm_is_volume.pbench_volume.*.id,
    count.index
  )
  name     = "${var.run_label}-pbench-attachment-${format("%02d", count.index)}"
  delete_volume_on_instance_delete = false
}