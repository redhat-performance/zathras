Role Name
=========

wait_for_ssh

Requirements
------------


Role Variables
--------------
	hostname: name of host to wait for.


Dependencies
------------


Example Playbook
----------------

- name: example wait for ssh to come up
  include_role:
    name: wait_for_ssh
  vars:
    hostname: "{{ example.public_dns_host0 }}"

License
-------

RHEL

Author Information
------------------

David Valin
