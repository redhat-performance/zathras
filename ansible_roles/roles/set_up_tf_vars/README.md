set_up_tf_vars
==============

Shared helper role that renders the Terraform variables file
(`{{ working_dir }}/tf/env.tfvars`) used by the cloud "create" roles.

It assembles the caller's base `tfvars.j2` with the per-run
`add_main_tf_vars` file, renders it through the `template` module, appends the
disk variables (parsed from `config_info.cloud_disks`), and finally strips the
`'_'` quoting workaround used to keep bare underscores in sku values.

Requirements
------------

This role has **no templates of its own**.  The calling role must supply, in
its own `templates/` directory:

* `tfvars.j2`       - base Terraform vars template
* `tfvars_disks.j2` - disk vars template, which consumes the `disk_type`,
  `disk_size`, `disk_count`, `disk_iops`, and `disk_tp` registered facts set
  by this role.

Ansible's role search path resolves those templates from the caller when this
role is included via `include_role`.

Role Variables
--------------

* `working_dir`             - run-time working directory.  Must already contain
  `add_main_tf_vars` and a `tf/` subdirectory.
* `config_info.cloud_disks` - disk specification string, or `"none"` to skip
  disk variable generation.

Produces
--------

* `{{ working_dir }}/tf/env.tfvars`

Dependencies
------------

Called by the cloud create roles: `aws_create`, `azure_create`,
`ibm_vpc_create`.

Example Playbook
----------------

    - name: set up the terraform vars
      include_role:
        name: set_up_tf_vars

License
-------

RHEL

Author Information
------------------

David Valin
