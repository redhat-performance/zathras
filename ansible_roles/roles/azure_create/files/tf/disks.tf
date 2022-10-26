resource "azurerm_managed_disk" "datadisk" {
  count                = var.vm_count * var.disk_count
  name                 = "${var.resource_group}-disk${count.index}"
  location             = var.location
  resource_group_name  = azurerm_resource_group.resource_group.name
  storage_account_type = var.disk_type
  create_option        = "Empty"
  disk_size_gb         = var.disk_size

  tags = {
    environment = "Zathras"
  }
}

resource "azurerm_virtual_machine_data_disk_attachment" "datadisk" {
  count              = var.vm_count * var.disk_count
  managed_disk_id    = element(azurerm_managed_disk.datadisk.*.id, count.index)
  virtual_machine_id = element(azurerm_linux_virtual_machine.virtualmachine.*.id, count.index)
  lun                = "${11+count.index}"
  caching            = "None"
}
