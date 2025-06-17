# And finally, create the virtual machine
resource "azurerm_linux_virtual_machine" "virtualmachine" {
    count                 = var.vm_count
    name                  = "${var.run_label}-vm"
    location              = var.location
    resource_group_name   = azurerm_resource_group.resource_group.name
    network_interface_ids = [ azurerm_network_interface.publicnic[count.index].id]
    size                  = var.machine_type
    admin_username        = var.test_user
    admin_ssh_key {
        username   = var.test_user
        public_key = file("~/.ssh/id_rsa.pub")
    }
    PRIORITYSPOT
    EVICTIONPOLICY

    os_disk {
        caching              = "ReadWrite"
        disk_size_gb         = 10
        storage_account_type = "Premium_LRS"
    }

    source_image_reference {
        publisher = var.publisher
        offer     = var.offer
        sku       = var.sku
        version   = var.azversion
    }
}
