variable "machine_type" {
  description = "IBM Cloud VSI profile (instance type)"
  type        = string
}

variable "cloud_os_version" {
  description = "OS version identifier"
  type        = string
}

variable "run_label" {
  description = "Label for this test run"
  type        = string
}

variable "region" {
  description = "IBM Cloud region"
  type        = string
  default     = "us-south"
}

variable "zone" {
  description = "IBM Cloud zone within region"
  type        = string
  default     = "us-south-1"
}

variable "test_user" {
  description = "User for SSH access"
  type        = string
}

variable "ssh_key_name" {
  description = "Name of SSH key in IBM Cloud"
  type        = string
}

variable "vm_image" {
  description = "IBM Cloud image ID"
  type        = string
}

variable "vm_count" {
  description = "Number of VSIs to create"
  type        = number
  default     = 1
}

variable "network_count" {
  description = "Number of additional networks"
  type        = number
  default     = 0
}

variable "vpc_name" {
  description = "Existing VPC name (if empty, creates new VPC)"
  type        = string
  default     = ""
}

variable "resource_group_id" {
  description = "IBM Cloud resource group ID"
  type        = string
  default     = ""
}
