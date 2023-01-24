resource "aws_ebs_volume" "disk_volume" {
  count             = var.disk_count * var.vm_count
  availability_zone = element(REPLACE.ec2.*.availability_zone, count.index)
  size              = var.disk_size
  type              = var.disk_type
  tags = {
    Name = var.run_label
  }
}

resource "aws_volume_attachment" "disk_attachement" {
  count       = var.vm_count * var.disk_count
  volume_id   = aws_ebs_volume.disk_volume.*.id[count.index]
  device_name = element(var.ec2_device_names, count.index)
  instance_id = element(REPLACE.ec2.*.terraform_id, count.index)
}
