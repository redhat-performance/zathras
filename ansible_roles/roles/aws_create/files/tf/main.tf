terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 3.27"
    }
  }
  required_version = ">= 0.14.9"
}

# Defines default values for the provider
provider "aws" {
  profile = "default"
  region  = var.region
  default_tags {
    tags = {
      User     = "${var.user}"
      Environment     = "${var.environment}"
      Project     = "${var.project}"
      Manager     = "${var.manager}"
      Owner       = "${var.owner}"
    }
  }
}
