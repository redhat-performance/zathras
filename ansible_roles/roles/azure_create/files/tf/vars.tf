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
  default = "RedHat:RHEL:8_4:8.4.2021081003"
}

variable "publisher" {
  type    = string
  default = "RedHat"
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

variable "pbench_device" {
  type    = string
  default =   "/dev/sdd"
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
