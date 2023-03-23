resource "aws_ebs_volume" "disk_volume_REPLACE_INDEX" {
  count             = var.disk_count * var.vm_count
  availability_zone = REPLACE_INST.ec2[REPLACE_INDEX].availability_zone
  size              = var.disk_size
  type              = var.disk_type
  tags = {
    Name = var.run_label
  }
}

resource "aws_volume_attachment" "disk_attachement_REPLACE_INDEX" {
  count       = var.vm_count * var.disk_count
  volume_id   = aws_ebs_volume.disk_volume_REPLACE_INDEX.*.id[count.index]
  device_name = element(var.ec2_device_names, count.index)
  instance_id = REPLACE_INST.ec2[REPLACE_INDEX].REPLACE_INSTANCE_ID
}
