# Create info, no spot and no network.
output "public_dns_host0" {
 value = REPLACE.ec2[0].public_dns
}
output "aws_instance_id0" {
 value = REPLACE.ec2[0].REPLACE_ID
}
output "aws_zoneid0" {
 value = REPLACE.ec2[0].availability_zone
}

