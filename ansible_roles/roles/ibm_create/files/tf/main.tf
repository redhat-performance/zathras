terraform {
  required_providers {
    ibm = {
      source  = "IBM-Cloud/ibm"
      version = "~> 1.70"
    }
  }
  required_version = ">= 1.0"
}

# Configure the IBM Cloud Provider
provider "ibm" {
  region = var.region
}

# Get the VPC
data "ibm_is_vpc" "zathras_vpc" {
  count = var.vpc_name != "" ? 1 : 0
  name  = var.vpc_name
}

# Get or create VPC
resource "ibm_is_vpc" "zathras_vpc" {
  count          = var.vpc_name == "" ? 1 : 0
  name           = "${var.run_label}-vpc-${formatdate("YYYYMMDDHHmmss", timestamp())}"
  resource_group = var.resource_group_id
  tags           = [var.User, var.Project]

  lifecycle {
    ignore_changes = [name]
  }
}

locals {
  vpc_id = var.vpc_name != "" ? data.ibm_is_vpc.zathras_vpc[0].id : ibm_is_vpc.zathras_vpc[0].id
}

# Create subnet
resource "ibm_is_subnet" "zathras_subnet" {
  name                     = "${var.run_label}-${var.machine_type}-subnet"
  vpc                      = local.vpc_id
  zone                     = var.zone
  total_ipv4_address_count = 256
  resource_group           = var.resource_group_id
}

# Create security group
resource "ibm_is_security_group" "zathras_sg" {
  name           = "${var.run_label}-${var.machine_type}-sg"
  vpc            = local.vpc_id
  resource_group = var.resource_group_id
}

# Security group rules - Allow all inbound
resource "ibm_is_security_group_rule" "zathras_sg_rule_inbound_all" {
  group     = ibm_is_security_group.zathras_sg.id
  direction = "inbound"
  remote    = "0.0.0.0/0"
}

# Security group rules - Allow all outbound
resource "ibm_is_security_group_rule" "zathras_sg_rule_outbound_all" {
  group     = ibm_is_security_group.zathras_sg.id
  direction = "outbound"
  remote    = "0.0.0.0/0"
}

# Get SSH key
data "ibm_is_ssh_key" "zathras_ssh_key" {
  name = var.ssh_key_name
}

# Create VSI (Virtual Server Instance)
resource "ibm_is_instance" "test" {
  count          = var.vm_count
  name           = "${var.run_label}-${var.machine_type}-${count.index}"
  vpc            = local.vpc_id
  zone           = var.zone
  profile        = var.machine_type
  image          = var.vm_image
  resource_group = var.resource_group_id

  keys = [data.ibm_is_ssh_key.zathras_ssh_key.id]

  primary_network_interface {
    subnet          = ibm_is_subnet.zathras_subnet.id
    security_groups = [ibm_is_security_group.zathras_sg.id]
  }

  # Dynamic network interfaces for additional networks
  dynamic "network_interfaces" {
    for_each = range(var.network_count)

    content {
      name            = "eth${network_interfaces.value + 1}"
      subnet          = ibm_is_subnet.zathras_private_subnet[network_interfaces.value].id
      security_groups = [ibm_is_security_group.zathras_sg.id]
    }
  }

  tags = [var.User, var.Project, var.run_label]

  lifecycle {
    ignore_changes = [image]
  }
}

# Create floating IP for public access
resource "ibm_is_floating_ip" "zathras_floating_ip" {
  count          = var.vm_count
  name           = "${var.run_label}-${var.machine_type}-fip-${count.index}"
  target         = ibm_is_instance.test[count.index].primary_network_interface[0].id
  resource_group = var.resource_group_id
  tags           = [var.User, var.Project]
}

# Create private subnets for additional networks
resource "ibm_is_subnet" "zathras_private_subnet" {
  count                    = var.network_count
  name                     = "${var.run_label}-${var.machine_type}-private-subnet-${count.index}"
  vpc                      = local.vpc_id
  zone                     = var.zone
  total_ipv4_address_count = 256
  resource_group           = var.resource_group_id
}
