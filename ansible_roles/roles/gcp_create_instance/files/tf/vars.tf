variable "machine_type" {
  type = string
}

variable "cloud_os_version" {
  type = string
}

variable "project_id" {
  type = string
}

variable "run_label" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "zone" {
  type    = string
  default = "us-central1-a"
}

variable "test_user" {
  type = string
}

variable "ssh_key_path" {
  type    = string
  default = "~/.ssh/id_rsa"
}

variable "vm_image" {
  type    = string
  default = "rhel-cloud/rhel-8"
}

variable "vm_count" {
  type    = number
  default = 1
}

variable "network_count" {
  type    = number
  default = 1
}

variable "disk_type" {
  type    = string
  default = ""
}

variable "disk_count" {
  type    = number
  default = 1
}

variable "disk_zone" {
  type    = string
  default = ""
}

variable "disk_size" {
  type    = string
  default = ""
}
