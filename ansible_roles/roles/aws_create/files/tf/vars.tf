variable "machine_type" {
  type = string
}

variable "cloud_os_version" {
  type = string
}

variable "cloud_placement" {
  type = string
}

variable "run_label" {
  type = string
  default = "none"
}

variable "region" {
  type    = string
  default = "none"
}

variable "vm_image" {
  type    = string
  default = "none"
}

variable "zone" {
  type    = string
  default = "none"
}

variable "test_user" {
  type = string
  default = "none"
}

variable "user" {
  type = string
  default = "none"
}

variable "ssh_key_path" {
  type    = string
  default = "none"
}

variable "ssh_public_key_path" {
  type    = string
  default = "~/.ssh/id_rsa.pub"
}

variable "security_group" {
  type    = string
  default = "none"
}

variable "key_name" {
  type    = string
  default = "none"
}

variable "vm_count" {
  type    = number
  default = 1
}

variable "network_count" {
  type    = number
  default = 1
}

variable "spot_price" {
  type    = string
}

variable "pb_disk_count" {
  default = 1
}

variable "pb_vol_size" {
  default = 512
}

variable "pb_disk_type" {
  default = "gp2"
}

variable "ec2_device_names" {
  default = [
    "/dev/sde",
    "/dev/sdf",
    "/dev/sdg",
    "/dev/sdh",
    "/dev/sdi",
    "/dev/sdj",
    "/dev/sdk",
    "/dev/sdl",
    "/dev/sdn",
    "/dev/sdo",
    "/dev/sdp",
    "/dev/sdq",
    "/dev/sdr",
    "/dev/sds,",
    "/dev/sdt",
    "/dev/sdu",
    "/dev/sdv",
    "/dev/sdw",
    "/dev/sdx",
    "/dev/sdy",
    "/dev/sdz",
  ]
}

variable "disk_type" {
  type = string
  default = "gp2"
}

variable "disk_count" {
  default = 0
}

variable "disk_size" {
  default = 0
}

variable "disk_iops" {
  default = 0
}

variable "disk_tp" {
  default = 0
}

variable "avail_zone" {
  default = "none"
}
