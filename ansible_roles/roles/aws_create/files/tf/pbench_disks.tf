resource "aws_ebs_volume" "pbench_volume" {
  count             = var.vm_count
  availability_zone = element(REPLACE.ec2.*.availability_zone, count.index)
  size              = "1500"
  type              = var.pb_disk_type
  tags = {
    Name = "pbench_${var.run_label}"
  }
}

resource "aws_volume_attachment" "volume_attachement" {
  count       = var.vm_count
  volume_id   = aws_ebs_volume.pbench_volume.*.id[count.index]
  device_name = var.pbench_device
  instance_id = element(REPLACE.ec2.*.id, count.index)
}
