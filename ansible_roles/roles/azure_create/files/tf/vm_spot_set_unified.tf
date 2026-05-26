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
        storage_account_type = "Premium_LRS"
    }

    # Use source_image_id for Azure Compute Gallery or managed images
    source_image_id = var.use_custom_image ? var.az_urn_sub : null

    # Use source_image_reference for marketplace images
    dynamic "source_image_reference" {
        for_each = var.use_custom_image ? [] : [1]
        content {
            publisher = var.publisher
            offer     = var.offer
            sku       = var.sku
            version   = var.azversion
        }
    }
}
