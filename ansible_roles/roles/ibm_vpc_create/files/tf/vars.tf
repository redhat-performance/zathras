variable "machine_type" {
  type = string
  default = "bx2-2x8"
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
  default = "us-south"
}

variable "zone" {
  type = string
  default = "us-south-1"
}

variable "resource_group" {
  type = string
  default = "none"
}

variable "run_label" {
  type = string
  default = "none"
}

variable "test_user" {
  type = string
  default = "none"
}

variable "ssh_key_name" {
  type = string
  default = "none"
}

variable "ibmcloud_api_key" {
  type = string
  description = "IBM Cloud API key"
  sensitive = true
}

variable "image_name" {
  type = string
  default = "ibm-redhat-8-4-minimal-amd64-1"
}

variable "vm_count" {
  type = number
  default = 1
}

variable "network_count" {
  type = number
  default = 1
}

variable "pbench_device" {
  type = string
  default = "/dev/vdd"
}

variable "pb_disk_count" {
  type = number
  default = 1
}

variable "pb_vol_size" {
  type = number
  default = 500
}

variable "pb_disk_profile" {
  type = string
  default = "general-purpose"
}

variable "disk_profile" {
  type = string
  default = "general-purpose"
}

variable "disk_count" {
  type = number
  default = 0
}

variable "disk_size" {
  type = number
  default = 100
}

variable "vpc_tags" {
  type = list(string)
  default = []
}