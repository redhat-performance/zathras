terraform {
  required_providers {
    ibm = {
      source = "IBM-Cloud/ibm"
      version = "~> 1.49.0"
    }
  }
  required_version = ">= 1.0"
}

provider "ibm" {
  region = var.region
  ibmcloud_api_key = var.ibmcloud_api_key
}

locals {
  tags = var.vpc_tags
}

# Define resource group
data "ibm_resource_group" "resource_group" {
  name = var.resource_group
}

# Create virtual private cloud
resource "ibm_is_vpc" "vpc" {
  name           = "${var.run_label}-vpc"
  resource_group = data.ibm_resource_group.resource_group.id
  tags           = local.tags
}

# Create public subnet
resource "ibm_is_subnet" "subnet" {
  name            = "${var.run_label}-subnet"
  vpc             = ibm_is_vpc.vpc.id
  zone            = var.zone
  ipv4_cidr_block = "10.240.0.0/24"
  resource_group  = data.ibm_resource_group.resource_group.id
}

# Create security group
resource "ibm_is_security_group" "security_group" {
  name           = "${var.run_label}-sg"
  vpc            = ibm_is_vpc.vpc.id
  resource_group = data.ibm_resource_group.resource_group.id
}

# Create security group rule for SSH
resource "ibm_is_security_group_rule" "security_group_rule_ssh" {
  group     = ibm_is_security_group.security_group.id
  direction = "inbound"
  remote    = "0.0.0.0/0"
  
  tcp {
    port_min = 22
    port_max = 22
  }
}

# Create security group rule for outbound traffic
resource "ibm_is_security_group_rule" "security_group_rule_outbound" {
  group     = ibm_is_security_group.security_group.id
  direction = "outbound"
  remote    = "0.0.0.0/0"
}

# Get SSH key data
data "ibm_is_ssh_key" "ssh_key" {
  name = var.ssh_key_name
}

# Create instances
resource "ibm_is_instance" "instance" {
  count          = var.vm_count
  name           = "${var.run_label}-instance-${format("%02d", count.index)}"
  vpc            = ibm_is_vpc.vpc.id
  zone           = var.zone
  profile        = var.machine_type
  image          = var.image_name
  keys           = [data.ibm_is_ssh_key.ssh_key.id]
  resource_group = data.ibm_resource_group.resource_group.id
  
  primary_network_interface {
    name            = "eth0"
    subnet          = ibm_is_subnet.subnet.id
    security_groups = [ibm_is_security_group.security_group.id]
  }
  
  # Placement group can be configured here if needed
  # PRIORITYSPOT - will be replaced by Ansible
  # EVICTIONPOLICY - will be replaced by Ansible
  
  tags = local.tags
}