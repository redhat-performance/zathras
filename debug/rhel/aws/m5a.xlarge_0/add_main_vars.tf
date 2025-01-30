provider "aws" {
  profile = "default"
  region  = var.region
  default_tags {
    tags = {
      User = "${var.User}"
      Owner = "${var.Owner}"
      Manager = "${var.Manager}"
      Project = "${var.Project}"
      Environment = "${var.Environment}"
      Jirald = "${var.Jirald}"
      TicketID = "${var.TicketID}"
    }
  }
}
