add_networks
============

Appends the Terraform `system` locals block to `{{ working_dir }}/tf/main.tf`.
The block is consumed by the cloud `main.tf` files via `for_each = local.system`,
which read `each.value.index` and `each.value.sys`.

The block is rendered from `templates/system_locals.j2` and inserted with
`blockinfile` (wrapped in an "ANSIBLE MANAGED BLOCK add_networks" marker) so the
role is idempotent and re-running it will not duplicate the block.

Requirements
------------

`{{ working_dir }}/tf/main.tf` must already exist (the calling role copies the
base `main.tf` in before including this role).

Role Variables
--------------

- `working_dir`: directory holding the generated Terraform (`tf/main.tf`).
- `config_info.host_config`: the host system config; emitted as system index 0.
- `config_info.cloud_numb_networks`: number of networks requested. When `0`, only
  system index 0 is emitted.
- `config_info.cloud_network_systems`: the system to connect to. When `"none"`,
  system index 1 reuses `host_config`; otherwise it is used as index 1's `sys`.

Dependencies
------------

None. Intended to be pulled in via `include_role` from the cloud create roles
(`aws_create`, `azure_create`, `ibm_vpc_create`).

Example Playbook
----------------

    - name: add in vars for networks
      include_role:
        name: add_networks

License
-------

Red Hat

Author Information
------------------

David Valin
