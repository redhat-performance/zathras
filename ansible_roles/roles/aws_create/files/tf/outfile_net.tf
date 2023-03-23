# Create info, no spot and no network.
output "public_dns_host1" {
 value = REPLACE_INST.ec2[1].public_dns
}
output "aws_instance_id1" {
 value = REPLACE_INST.ec2[1].REPLACE_ID
}
output "aws_zoneid1" {
 value = REPLACE_INST.ec2[1].availability_zone
}
