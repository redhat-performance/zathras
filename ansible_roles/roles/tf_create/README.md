tf_create
=========

Create cloud resources with terraform.

This role runs the terraform lifecycle against the generated terraform
configuration in `{{ working_dir }}/tf`:

1. `terraform init`
2. Create/select a terraform workspace named
   `<system_type>-<run_label>-<host_or_cloud_inst>`
3. `terraform plan` (using `env.tfvars`) into a saved plan (`plan.tfplan`)
4. `terraform apply` of the saved plan

On any failure the role cleans up partial resources by invoking the
`tf_delete` role and then aborts the play (see `tasks/tf_bail.yml`).

Tasks
-----
	tasks/main.yml    orchestrates init then apply
	tasks/tf_init.yml init, workspace, and plan
	tasks/tf_apply.yml apply the plan and record the return code
	tasks/tf_bail.yml  clean up partial resources and abort on failure

Roles called:
	tf_delete (only on failure, to clean up partial resources)

Commands called:
	terraform init
	terraform workspace new / select
	terraform plan
	terraform apply

Requirements
------------

	terraform available on the PATH.
	The terraform configuration and variables must already be generated into
	`{{ working_dir }}/tf` (see the set_up_tf_vars role) before this role runs.

Role Variables
--------------
	working_dir: directory holding the tf/ configuration and state files
	config_info.system_type: used to build the workspace name
	config_info.run_label: used to build the workspace name
	config_info.host_or_cloud_inst: used to build the workspace name

Outputs / updated data
----------------------
	{{ working_dir }}/tf.rtc: the return code of the terraform operation,
		written as "rtc: 0" on success or "rtc: 1" on failure.  The file is
		created if it does not already exist.
	{{ working_dir }}/tf/terraform_plan.out: captured plan output
	{{ working_dir }}/tf/terraform_apply.out: captured apply output

Dependencies
------------

Depends on the cloud automation having generated the terraform config.

Example Playbook
----------------

- hosts: local
  vars_files: ansible_vars.yml
  tasks:
    - name: tf_create
      include_role:
        name: tf_create

License
-------

RHEL

Author Information
------------------

David Valin
