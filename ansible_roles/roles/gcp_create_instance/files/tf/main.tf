terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "3.5.0"
    }
  }
}

# Defines default values for the provider
provider "google" {

  project = var.project_id
  region  = var.region
}

