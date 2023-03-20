terraform {
  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
      version = "~>2.0"
    }
  }
}
provider "azurerm" {
  features {}
}


# Create virtual network
resource "azurerm_virtual_network" "virtual_network" {
    name                = "${var.run_label}-vnet"
    address_space       = ["10.0.0.0/16"]
    location            = var.location
    resource_group_name = azurerm_resource_group.resource_group.name
}

# Create subnet
resource "azurerm_subnet" "subnet" {
    name                 = "${var.run_label}-subnet"
    resource_group_name  = azurerm_resource_group.resource_group.name
    virtual_network_name = azurerm_virtual_network.virtual_network.name
    address_prefixes     = ["10.0.1.0/24"]
}

# Create public IP
resource "azurerm_public_ip" "publicip" {
    count                = var.vm_count
    name                 = "${var.run_label}-publicip-${format("%02d",count.index)}"
    location             = var.location
    resource_group_name  = azurerm_resource_group.resource_group.name
    allocation_method    = "Dynamic"
}

# Create Network Security Group and rule
resource "azurerm_network_security_group" "nsg" {
    name                = "${var.run_label}-nsg"
    location            = var.location
    resource_group_name = azurerm_resource_group.resource_group.name

    security_rule {
        name                       = "SSH"
        priority                   = 1001
        direction                  = "Inbound"
        access                     = "Allow"
        protocol                   = "Tcp"
        source_port_range          = "*"
        destination_port_range     = "22"
        source_address_prefix      = "*"
        destination_address_prefix = "*"
    }
}

# Create network interface
resource "azurerm_network_interface" "publicnic" {
    count               = var.vm_count
    name                = "${var.run_label}-publicnic${format("%02d",count.index)}"
    location            = var.location
    resource_group_name = azurerm_resource_group.resource_group.name

    ip_configuration {
        name                          = "${var.run_label}-pubnicconfig"
        subnet_id                     = azurerm_subnet.subnet.id
        private_ip_address_allocation = "Dynamic"
        public_ip_address_id          = element(azurerm_public_ip.publicip.*.id,count.index)
    }
}

# Connect the security group to the network interface
resource "azurerm_subnet_network_security_group_association" "nsg_assoc" {
    #network_interface_id     = azurerm_network_interface.publicnic.id
    subnet_id = azurerm_subnet.subnet.id
    network_security_group_id = azurerm_network_security_group.nsg.id
}

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

    os_disk {
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
