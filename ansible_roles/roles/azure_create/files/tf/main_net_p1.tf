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

# Create resource group
resource "azurerm_resource_group" "resource_group" {
    name     = var.resource_group
    location = var.location

    tags = {
        environment = "${var.run_label}"
    }
    timeouts {
        delete = "15m"
    }
}

# Create virtual network
resource "azurerm_virtual_network" "virtual_network" {
    name                = "${var.run_label}-vnet"
    address_space       = ["10.0.0.0/16"]
    location            = var.location
    resource_group_name = azurerm_resource_group.resource_group.name
    tags = {
        environment = var.run_label
    }
}

# Create subnet
resource "azurerm_subnet" "subnet" {
    name                 = "${var.run_label}-subnet"
    resource_group_name  = azurerm_resource_group.resource_group.name
    virtual_network_name = azurerm_virtual_network.virtual_network.name
    address_prefixes     = ["10.0.1.0/24"]
}

# Create privatesubnet
#
# Note: we only support one private network at this time.  If in the future we support
# multiple private networks, this will need to be updated.
#
resource "azurerm_subnet" "subnet-prvt" {
    name                 = "${var.run_label}-subnet-prvt"
    virtual_network_name = azurerm_virtual_network.virtual_network.name
    resource_group_name  = azurerm_resource_group.resource_group.name
    address_prefixes     = ["10.0.2.0/24"]
}

# Create public IP
resource "azurerm_public_ip" "publicip" {
    count                = var.vm_count
    name                 = "${var.run_label}-publicip-${format("%02d",count.index)}"
    location             = var.location
    resource_group_name  = azurerm_resource_group.resource_group.name
    allocation_method    = "Dynamic"

    tags = {
        environment = "${var.run_label}"
    }
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

    tags = {
        environment = "${var.run_label}"
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

    tags = {
        environment = "${var.run_label}"
    }
}

resource "azurerm_network_interface" "testnic1" {
  count               = var.vm_count
  name                = "${var.run_label}-${format("%02d",count.index)}"
  location            = "${var.location}"
  resource_group_name  = azurerm_resource_group.resource_group.name
  ip_configuration {
    name                          = "${var.run_label}-private"
    subnet_id                     = azurerm_subnet.subnet-prvt.id
    private_ip_address_allocation = "Dynamic"
  }
}

# Connect the security group to the network interface
resource "azurerm_subnet_network_security_group_association" "nsg_assoc" {
    subnet_id = azurerm_subnet.subnet.id
    network_security_group_id = azurerm_network_security_group.nsg.id
}
