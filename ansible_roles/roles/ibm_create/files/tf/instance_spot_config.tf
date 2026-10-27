# Spot instance configuration for IBM Cloud VSIs
# This file is appended to main.tf when use_spot_instances is true

  commitment_term = 1
  dedicated_host  = null
