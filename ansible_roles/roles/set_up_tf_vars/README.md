Role Name
=========

This is a work in progress, and will be updated over time.

Terminate the instances created, including storage and networks

Roles called: 
	aws_remove_instance
	aws_net_terminate
Commands called:
	aws ec2 delete-volume --volume-id
	aws ec2 attach-volume
	sleep

Updated data: None

Files used:
	vol_info: contains the volume information
	ansible_run_vars.yml: run time information
	ansible_vars.yml:  test configuration information


Requirements
------------


Role Variables
--------------
	aws_instance_id: id of the instance removing
	aws_net_instance_id: id of the network instance removing
	cloud_numb_networks: number of networks allocated to the instance (minus the default)


Dependencies
------------

Depends on the cloud auto.

Example Playbook
----------------

- hosts: local
  vars_files: ansible_vars.yml
  tasks:
    - name: aws_terminate
      include_role:
        name: aws_terminate
      when:
        - config_info.cd_vendor == "aws"
        - config_info.cloud_terminate_instance == 1


License
-------

RHEL

Author Information
------------------

David Valin
