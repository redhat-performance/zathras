resource "azurerm_managed_disk" "pbench_volume" {
  count                = var.vm_count
  name                 = "${var.resource_group}-pbench${count.index}"
  location             = var.location
  resource_group_name  = azurerm_resource_group.resource_group.name
  storage_account_type = var.disk_type
  create_option        = "Empty"
  disk_size_gb         = "1500"
}

resource "azurerm_virtual_machine_data_disk_attachment" "pbenchdisk" {
  count              = var.vm_count
  managed_disk_id    = element(azurerm_managed_disk.pbench_volume.*.id, count.index)
  virtual_machine_id = azurerm_linux_virtual_machine.virtualmachine[count.index].id
  lun                = "10"
  caching            = "ReadWrite"
}
