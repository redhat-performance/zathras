# And finally, create the virtual machine
resource "azurerm_linux_virtual_machine" "virtualmachine" {
    for_each             = local.system
    name                  = "${var.run_label}-vm-${format("%02d",each.value.index)}"
    location              = var.location
    resource_group_name   = azurerm_resource_group.resource_group.name
    network_interface_ids = ["${azurerm_network_interface.publicnic[each.value.index].id}","${azurerm_network_interface.testnic1[each.value.index].id}"]
    size                  = each.value.sys
    admin_username        = var.test_user

    admin_ssh_key {
        username   = var.test_user
        public_key = file("~/.ssh/id_rsa.pub")
    }

    os_disk {
        name                 = "${var.run_label}-OS_Disk-${format("%02d",each.value.index)}"
        caching              = "ReadWrite"
        storage_account_type = "Premium_LRS"
    }

    source_image_reference {
        publisher = var.publisher
        offer     = var.offer
        sku       = var.sku
        version   = var.azversion
    }
}

data "azurerm_public_ip" "publicip" {
    count               = var.vm_count
    name                = azurerm_public_ip.publicip[count.index].name
    resource_group_name = azurerm_linux_virtual_machine.virtualmachine[count.index].resource_group_name
}

# Need to put data out for private
data "azurerm_network_interface" "testnic1" {
    count               = var.vm_count
    name                = azurerm_network_interface.testnic1[count.index].name
    resource_group_name = azurerm_linux_virtual_machine.virtualmachine[count.index].resource_group_name
}
