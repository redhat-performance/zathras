terraform {
  required_providers {
    ibm = {
      source  = "IBM-Cloud/ibm"
      version = "~> 1.70"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
  required_version = ">= 1.0"
}

resource "random_id" "suffix" {
  byte_length = 4
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
  name           = "${local.name_prefix}-vpc"
  resource_group = var.resource_group_id
  tags           = [var.User, var.Project]
}

locals {
  vpc_id = var.vpc_name != "" ? data.ibm_is_vpc.zathras_vpc[0].id : ibm_is_vpc.zathras_vpc[0].id
  # IBM Cloud caps names at 63 chars. Longest pattern here is
  # "<run_label>-<suffix>-<machine_type>-private-subnet-<idx>": 9 (suffix) +
  # 20 (worst-case machine_type) + 16 ("-private-subnet-") + 2 (idx) = 47
  # reserved, leaving 15 chars for run_label.
  run_label_safe = substr(var.run_label, 0, 15)
  name_prefix    = "${local.run_label_safe}-${random_id.suffix.hex}"
}

# Create subnet
resource "ibm_is_subnet" "zathras_subnet" {
  name                     = "${local.name_prefix}-${var.machine_type}-subnet"
  vpc                      = local.vpc_id
  zone                     = var.zone
  total_ipv4_address_count = 256
  resource_group           = var.resource_group_id
}

# Create security group
resource "ibm_is_security_group" "zathras_sg" {
  name           = "${local.name_prefix}-${var.machine_type}-sg"
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

# IBM Cloud VSIs must reference a pre-registered SSH key. Two mutually exclusive inputs:
#
# 1. ssh_key_id is set: use it as-is. This is the CI/CPT path (IBM_SSH_KEY_ID) for a
#    key created in the same job, persistent or not. No by-name lookup, so a
#    just-created key does not need to show up in `ibmcloud is keys` yet. A
#    long-lived local key is not required.
# 2. ssh_key_id is empty: look the key up by ssh_key_name (any existing key,
#    typically a long-lived one on local/interactive runs). Ansible matches the
#    local private-key fingerprint to an IBM Cloud key and fails before Terraform
#    if none exist.
data "ibm_is_ssh_key" "zathras_ssh_key" {
  count = var.ssh_key_id == "" ? 1 : 0
  name  = var.ssh_key_name
}

locals {
  ssh_key_id = var.ssh_key_id != "" ? var.ssh_key_id : data.ibm_is_ssh_key.zathras_ssh_key[0].id
}

# Create VSI (Virtual Server Instance)
resource "ibm_is_instance" "test" {
  count          = var.vm_count
  name           = "${local.name_prefix}-${var.machine_type}-${count.index}"
  vpc            = local.vpc_id
  zone           = var.zone
  profile        = var.machine_type
  image          = var.vm_image
  resource_group = var.resource_group_id

  # CI: var.ssh_key_id (no persistent key needed). Local: lookup by ssh_key_name.
  keys = [local.ssh_key_id]

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
  name           = "${local.name_prefix}-${var.machine_type}-fip-${count.index}"
  target         = ibm_is_instance.test[count.index].primary_network_interface[0].id
  resource_group = var.resource_group_id
  tags           = [var.User, var.Project]
}

# Create private subnets for additional networks
resource "ibm_is_subnet" "zathras_private_subnet" {
  count                    = var.network_count
  name                     = "${local.name_prefix}-${var.machine_type}-private-subnet-${count.index}"
  vpc                      = local.vpc_id
  zone                     = var.zone
  total_ipv4_address_count = 256
  resource_group           = var.resource_group_id
}
