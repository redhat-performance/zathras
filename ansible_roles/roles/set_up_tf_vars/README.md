set_up_tf_vars
==============

Renders the terraform variables file (`tf/env.tfvars`) used to create a cloud
instance, from templates supplied by the calling cloud role.

Important: this role has no `templates/` directory of its own. Each cloud role
that calls it must provide, in its own `templates/` directory:

- `tfvars.j2`        - the main terraform variables template
- `tfvars_disks.j2`  - the per-disk terraform variables template

These are reached via `include_role`'s search path (the `../templates/`
reference in `tasks/main.yml`).

Requirements
------------

The caller must provide the two templates above and pass `cloud_change_to`
(consumed inside `tfvars.j2`). The following files must exist in `working_dir`:

- `add_main_tf_vars` - extra tag variables appended to the rendered template
- `tf/`              - output directory for `env.tfvars`

Role Variables
--------------

- `working_dir`            - working directory holding inputs and the `tf/` output dir
- `cloud_change_to`        - target cloud (e.g. `azure`, `aws_instance`, `ibm_vpc`); used by `tfvars.j2`
- `config_info.cloud_disks`- disk spec list `"count:type:size:index:iops:tp"`, or `"none"`

What it does
------------

1. Copies the caller's `tfvars.j2` into `working_dir` and appends
   `add_main_tf_vars` to it.
2. Templates it into `tf/env.tfvars`.
3. If `cloud_disks` is not `"none"`, parses the disk spec and appends the
   rendered `tfvars_disks.j2` block.
4. Restores underscores that ansible would otherwise strip from the azure sku
   (`'_'` -> `_`).

Callers
-------

`aws_create`, `azure_create`, `ibm_vpc_create` (and the `tfvars.j2` /
`tfvars_disks.j2` templates also exist for `gcp_create_instance` and
`ibm_create`).
