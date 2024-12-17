# Defines a VM
#

resource "aws_network_interface" "zathras_nic1" {
  subnet_id       = aws_subnet.zathras_prvt_sn.id
  private_ips     = ["10.0.25.100"]
  security_groups = [aws_security_group.zathras_aws_prvt_sg.id]
  attachment {
    instance     = REPLACE_INST.ec2[0].REPLACE_ID
    device_index = 1
  }
}
resource "aws_network_interface" "zathras_nic2" {
  subnet_id       = aws_subnet.zathras_prvt_sn.id
  private_ips     = ["10.0.25.101"]
  security_groups = [aws_security_group.zathras_aws_prvt_sg.id]
  attachment {
    instance     = REPLACE_INST.ec2[1].REPLACE_ID
    device_index = 1
  }
}
