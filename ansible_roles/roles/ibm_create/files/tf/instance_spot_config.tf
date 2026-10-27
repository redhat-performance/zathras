# Spot instance configuration for IBM Cloud VSIs — intentionally empty.
#
# commitment_term is not a valid argument on ibm_is_instance (confirmed
# against the real terraform-provider-ibm v1.89.0 schema: no "commit",
# "spot", or "preemptible" argument exists on this resource at all).
# dedicated_host = null is a no-op (same as leaving it unset).
#
# var.use_spot_instances is plumbed through end-to-end but there is
# currently no known terraform-provider-ibm mechanism to actually request
# spot/preemptible pricing for a VPC VSI. Needs further research before
# this can do anything real; left empty rather than emitting invalid HCL.
