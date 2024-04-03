Role Name
=========
Creates the requested AWS image.  Due to the nature of AWS NICs we use a bash script to 
perform the network attachements.

Note: Support for spot is present, but is currently not used.  There is currently 
an issue with terraform aws spot creation, where we do not get the availability_zone
returned to us by terraform.  This prevents the creation of storage at the same time we create 

Files used to create the terraform templates.  Difference between spot and non spot files is
spot uses aws_spot_instance_request and non spot uses aws_instance.
files/tf 
=======
disks_ns.tf
disks_spot.tf
main_ns.tf
main_spot.tf:
outfile_ns_wn.tf
outfile_spot_wn.tf
outfile_ns_nn.tf
outfile_spot_nn.tf
pbench_ns_disks.tf
vars.tf

Ansible modules
tasks
======
aws_instance_create.yml
aws_place_zone.yml
aws_post_pbench.yml
aws_record_info.yml
aws_record_net_info.yml
aws_save_net_info.yml
aws_terraform_spot.yml
aws_terraform_spot_create.yml
aws_terraform_spot_create_needed.yml
aws_vpc.yml
main.yml


Requirements
------------


Role Variables
--------------

Dependencies
------------

Depends on the zathras kit.

Example Playbook
----------------
  - name: aws operations
    block:
    - name: aws_operations
      include_role:
        name: aws_create

    - name: create networks if need be
      include_role:
        name: aws_create_network_client
      when: config_info.cloud_numb_networks > 0
    when: config_info.cd_vendor == "aws"


License
-------

Red Hat

Author Information
------------------

David Valin
