resource "aws_ebs_volume" "pbench_volume_REPLACE_INDEX" {
  count             = var.vm_count
  availability_zone = REPLACE_INST.ec2[REPLACE_INDEX].availability_zone
  size              = "1500"
  type              = var.pb_disk_type
  tags = {
    Name = "pbench_${var.run_label}"
  }
}

resource "aws_volume_attachment" "volume_attachement_REPLACE_INDEX" {
  count       = var.vm_count
  volume_id   = aws_ebs_volume.pbench_volume_REPLACE_INDEX.*.id[count.index]
  device_name = var.pbench_device
  instance_id = REPLACE_INST.ec2[REPLACE_INDEX].REPLACE_INSTANCE_ID
}
