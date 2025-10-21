variable "machine_type" {
  type = string
  default = "Standard_D8s_v3"
}

variable "cloud_os_version" {
  type = string
  default = "none"
}

variable "cloud_placement" {
  type = string
}

variable "region" {
  type = string
  default = "eastus"
}

variable "project_id" {
  type = string
  default = "none"
}

variable "run_label" {
  type = string
  default = "none"
}

variable "location" {
  type    = string
  default = "eastus2"
}

variable "test_user" {
  type = string
  default = "none"
}

variable "resource_group" {
  type = string
  default = "none"
}

variable "ssh_key_path" {
  type    = string
  default = "~/.ssh/id_rsa"
}

variable "vm_image" {
  type    = string
  default = "none"
}

variable "az_subscription" {
  type    = string
  default = "none"
}

variable "publisher" {
  type    = string
  default = "RedHat"
}

variable "az_urn_sub" {
  type    = string
  default = "none"
}

variable "offer" {
  type    = string
  default = "RHEL"
}

variable "sku" {
  type    = string
  default = "8-LVM"
}

variable "azversion" {
  type    = string
  default = "latest"
}

variable "vm_count" {
  type    = number
  default = 1
}

variable "network_count" {
  type    = number
  default = 1
}

variable "pb_disk_count" {
  type    = number
  default = 1
}

variable "pb_vol_size" {
  type    = number
  default = 512
}

variable "pb_disk_type" {
  type    = string
  default = "Premium_LRS"
}

variable "disk_type" {
  type    = string
  default = "Premium_LRS"
}

variable "disk_count" {
  type    = number
  default = 0
}

variable "disk_size" {
  type    = string
  default = ""
}
