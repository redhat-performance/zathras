# Defines a VM

provider "aws" {
    alias = "zathras_prov"
    region = "${var.region}"
    default_tags {
      tags = {
        User = "${var.User}"
        Owner = "${var.Owner}"
        Manager = "${var.Manager}"
        Project = "${var.Project}"
        Environment = "${var.Environment}"
        Jirald = "${var.Jirald}"
        TicketID = "${var.TicketID}"
        app-code = "${var.app_code}"
        service-phase = "${var.service_phase}"
        cost-center = "${var.cost_center}"
      }
    }
}

resource "aws_vpc" "zathras_vpc" {
    provider = aws.zathras_prov
    enable_dns_support = true
    enable_dns_hostnames = true
    tags = {
      User = "${var.User}"
      Owner = "${var.Owner}"
      Manager = "${var.Manager}"
      Project = "${var.Project}"
      Environment = "${var.Environment}"
      Jirald = "${var.Jirald}"
      TicketID = "${var.TicketID}"
      app-code = "${var.app_code}"
      service-phase = "${var.service_phase}"
      cost-center = "${var.cost_center}"
    }
#
# Uncomment when using ipv6
#
#    assign_generated_ipv6_cidr_block = true
    cidr_block = "170.0.0.0/16"
}

resource "aws_subnet" "zathras_sn" {
    provider = aws.zathras_prov
    vpc_id = "${aws_vpc.zathras_vpc.id}"
    cidr_block = "${cidrsubnet(aws_vpc.zathras_vpc.cidr_block, 4, 1)}"
    map_public_ip_on_launch = true
    availability_zone = "${var.avail_zone}"
#
# Uncomment when using ipv6
#
#    ipv6_cidr_block = "${cidrsubnet(aws_vpc.zathras_vpc.ipv6_cidr_block, 8, 1)}"
#    assign_ipv6_address_on_creation = true
}

resource "aws_internet_gateway" "zathras_gw" {
    provider = aws.zathras_prov
    vpc_id = "${aws_vpc.zathras_vpc.id}"
}

resource "aws_default_route_table" "zathras_df_rt_tbl" {
    provider = aws.zathras_prov
    default_route_table_id = "${aws_vpc.zathras_vpc.default_route_table_id}"

    route {
        cidr_block = "0.0.0.0/0"
        gateway_id = "${aws_internet_gateway.zathras_gw.id}"
    }
#
# Uncomment when using ipv6
#
#    route {
#        ipv6_cidr_block = "::/0"
#        gateway_id = "${aws_internet_gateway.zathras_gw.id}"
#    }
}

resource "aws_route_table_association" "zathras_aws_rta" {
    provider = aws.zathras_prov
    subnet_id      = "${aws_subnet.zathras_sn.id}"
    route_table_id = "${aws_default_route_table.zathras_df_rt_tbl.id}"
}

resource "aws_security_group" "zathras_aws_sg" {
    provider = aws.zathras_prov
    name = "zathras_sg"
    vpc_id = "${aws_vpc.zathras_vpc.id}"
    ingress {
        from_port = 22
        to_port = 22
        protocol = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }
#
# Uncomment when using ipv6
#
#    ingress {
#        from_port = 0
#        to_port = 0
#        protocol = "-1"
#        ipv6_cidr_blocks = ["::/0"]
#    }
    egress {
      from_port = 0
      to_port = 0
      protocol = "-1"
      cidr_blocks = ["0.0.0.0/0"]
    }
#
# Uncomment when using ipv6
#
#    egress {
#      from_port = 0
#      to_port = 0
#      protocol = "-1"
#      ipv6_cidr_blocks = ["::/0"]
#    }
}


resource "aws_vpc" "zathras_prvt_vpc" {
    provider = aws.zathras_prov
    enable_dns_support = false
    enable_dns_hostnames = false
#
# Uncomment when using ipv6
#
#    assign_generated_ipv6_cidr_block = true
    cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "zathras_prvt_sn" {
    provider = aws.zathras_prov
    vpc_id = "${aws_vpc.zathras_prvt_vpc.id}"
    cidr_block = "${cidrsubnet(aws_vpc.zathras_prvt_vpc.cidr_block, 4, 1)}"
    map_public_ip_on_launch = false
    availability_zone = "${var.avail_zone}"
#
# Uncomment when using ipv6
#
#    ipv6_cidr_block = "${cidrsubnet(aws_vpc.zathras_vpc.ipv6_cidr_block, 8, 1)}"
#    assign_ipv6_address_on_creation = true
}

resource "aws_security_group" "zathras_aws_prvt_sg" {
    provider = aws.zathras_prov
    name = "zathras_sg"
    vpc_id = "${aws_vpc.zathras_prvt_vpc.id}"
    ingress {
        from_port = 0
        to_port = 65535
        protocol = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }
    egress {
      from_port = 0
      to_port = 0
      protocol = "-1"
      cidr_blocks = ["0.0.0.0/0"]
    }
}
