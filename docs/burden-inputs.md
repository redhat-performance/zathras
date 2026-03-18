# Burden Input Reference

Version: 3.2

## Overview

`burden` is the main execution tool of the Zathras automation framework. It supports two operating modes:
1. **Mode 1**: Reads a scenario file, parses arguments, and calls back onto itself with parsed arguments
2. **Mode 2**: Takes arguments and generates required Ansible YAML files, then invokes tests

## General Options

### System Configuration

| Option | Arguments | Description |
|--------|-----------|-------------|
| <nobr>`--system_type`</nobr> | `<vendor>` | Cloud vendor or local system. Valid values: `aws`, `azure`, `gcp`, `ibm`, `local` |
| <nobr>`--host_config`</nobr> | `<config>` | System specification and configuration (see [Host Configuration Format](#host-configuration-format)) |
| <nobr>`--max_systems`</nobr> | `<n>` | Maximum number of burden subinstances (cloud/local systems) created from parent. Default: 3 |

### Test Configuration

| Option | Arguments | Description |
|--------|-----------|-------------|
| <nobr>`--tests`</nobr> | `<test>` | Test name(s) to execute. Use comma-separated list: `test1,test2`. Overrides all other test options |
| <nobr>`--test_iter`</nobr> | `<iterations>` | Number of test iterations. For cloud instances, terminates and recreates image per iteration. Default: 1 |
| <nobr>`--test_def_file`</nobr> | `<file>` | Test definition file to use |
| <nobr>`--test_def_dir`</nobr> | `<dir>` | Test definition directory. Default: `<execution dir>/config`. Supports git repos with `https:` or `git:` prefix |
| <nobr>`--test_override`</nobr> | `<options>` | Override options for specific test in scenario file (see [Test Override Format](#test-override-format)) |
| <nobr>`--show_tests`</nobr> | - | List available tests as defined in `config/test_defs.yml` |
| <nobr>`--test_versions`</nobr> | `<test>,<test>,...` | Show available versions and descriptions for specified tests (git repos only) |
| <nobr>`--test_version_check`</nobr> | - | Check if running latest test versions, then exit. Default: no |
| <nobr><span style="white-space:nowrap;">`--update_test_versions`</span></nbsp> | - | Update templates to latest test versions (git repos only) |

### Scenario Files

| Option | Arguments | Description |
|--------|-----------|-------------|
| <nobr>`--scenario`</nobr> | `<file>` | Read and execute scenario definition file. Supports git repos with `https:` or `git:` prefix. Lines starting with `#` are comments. Lines starting with `%` replace strings: `% <current>=<new>` |
| <nobr>`--scenario_vars`</nobr> | `<file>` | Variable file for scenario file. Default: `config/zathras_scenario_vars_def` |
| <nobr>`--individ_vars`</nobr> | `<file>` | Individual burden settings file. Takes precedence over scenario file but overridden by command line. Default: `config/zathras_specific_vals_def` |

### Results and Logging

| Option | Arguments | Description |
|--------|-----------|-------------|
| <nobr>`--results_prefix`</nobr> | `<prefix>` | Run directory prefix |
| <nobr>`--archive`</nobr> | `<dir>/<results>` | Location to save archive information |
| <nobr>`--persistent_log`</nobr> | - | Enable persistent logging |
| <nobr>`--retry_failed_tests`</nobr> | `0`/`1` | Retry detected failed tests if set to 1. Default: 1 |
| <nobr>`--ansible_noise_level`</nobr> | `<level>` | Ansible output verbosity. Values: `normal` (standard), `dense` (task names only), `silence` (nothing) |

### Operating System Configuration

| Option | Arguments | Description |
|--------|-----------|-------------|
| <nobr>`--os_vendor`</nobr> | `<vendor>` | OS provider. Valid values: `rhel`, `ubuntu`, `amazon`, `suse`, `private`, `none` |
| <nobr>`--selinux_level`</nobr> | `<level>` | SELinux enforcement level. Values: `enforcing`, `permissive`, `disabled` |
| <nobr>`--selinux_state`</nobr> | `<state>` | SELinux state. Values: `enabled`, `disabled` |
| <nobr>`--java_version`</nobr> | `<version>` | Java version to install. Values: `java-8`, `java-11`, `java-17`, `java-21` |
| <nobr>`--tuned_profiles`</nobr> | `<profiles>` | Comma-separated list of tuned profiles (RHEL only). For cloud environments, each profile creates a distinct instance |
| <nobr>`--tuned_reboot`</nobr> | - | Reboot when new tuned profile is set. Default: no reboot |

### Package Management

| Option | Arguments | Description |
|--------|-----------|-------------|
| <nobr>`--no_packages`</nobr> | - | Do not install any packages (sets both no_pip_packages and no_system_packages). Default: no |
| <nobr>`--no_pip_packages`</nobr> | - | Do not install pip packages. Default: no |
| <nobr>`--no_system_packages`</nobr> | - | Do not install system packages (via dnf/apt/etc). Default: no |
| <nobr>`--package_name`</nobr> | `<name>` | Override default package set in test config. Format: `<os>_pkg` becomes `<os>_pkg_<ver>` |
| <nobr>`--upload_rpms`</nobr> | `<rpm1>,<rpm2>,...` | Comma-separated list of RPMs (full paths) to upload and install |
| <nobr>`--mode`</nobr> | `<mode>` | Operating mode. Use `image` for bootc-based hosts (skips packages, uses safe upload paths) |

### Update and Repository Options

| Option | Arguments | Description |
|--------|-----------|-------------|
| <nobr>`--update_target`</nobr> | `<image>` | Image to update. Only one update image can be used |
| <nobr>`--ignore_repo_errors`</nobr> | - | Ignore repository errors. Default: abort run on repo errors |
| <nobr>`--git_timeout`</nobr> | `<seconds>` | Timeout for git requests. Default: 60 |

### SSH and Authentication

| Option | Arguments | Description |
|--------|-----------|-------------|
| <nobr>`--ssh_key_file`</nobr> | `<file>` | SSH key file to use for authentication |
| <nobr>`--test_user`</nobr> | `<user>` | Username to log into system with. Overrides cloud/local defaults |
| <nobr>`--ibm_api_key`</nobr> | `<key>` | IBM Cloud API key (IBM Cloud only) |

### Execution Control

| Option | Arguments | Description |
|--------|-----------|-------------|
| <nobr>`--use_pcp`</nobr> | `0`/`1` | Enable (1) or disable (0) PCP usage by wrappers. Default: 1 |
| <nobr>`--preflight_check`</nobr> | - | Perform checks on scenario file and Zathras, then exit |
| <nobr>`--child`</nobr> | - | Indicate burden is a child process; skip initial setup work |
| <nobr>`--kit_upload_directory`</nobr> | `<path>` | Full path to upload directory. If not present, Zathras uses filesystem with most space |
| <nobr>`--no_clean_up`</nobr> | - | Do not clean up at end of test |

### Information and Help

| Option | Arguments | Description |
|--------|-----------|-------------|
| <nobr>`-h`, `--usage`</nobr> | - | Display condensed usage information |
| <nobr>`--verbose`</nobr> | - | Display verbose usage message |
| <nobr>`--show_os_versions`</nobr> | - | Show available OS versions for specified cloud type and OS vendor |

## Cloud-Specific Options

### Cloud Instance Configuration

| Option | Arguments | Description |
|--------|-----------|-------------|
| <nobr>`--cloud_os_id`</nobr> | `<os_id>` | OS image ID (e.g., AWS AMI number). For multiple architectures: `x86:ami-xxx,arm64:ami-yyy` |
| <nobr>`--create_only`</nobr> | - | Only perform VM creation and OS installation, then stop |
| <nobr>`--terminate_cloud`</nobr> | `0`/`1` | Terminate (1) or leave running (0) cloud instance. Default: 1 (terminate) |
| <nobr>`--create_attempts`</nobr> | `<n>` | Number of attempts to create instance with designated CPU type. Default: 5 |

### Spot Instances

| Option | Arguments | Description |
|--------|-----------|-------------|
| <nobr>`--use_spot`</nobr> | `<0/1>` | Use spot pricing based on `config/spot_price.cfg`. Default: no |
| <nobr>`--no_spot_recover`</nobr> | - | Do not recover from spot instance termination |

### Terraform Operations

| Option | Arguments | Description |
|--------|-----------|-------------|
| <nobr>`--tf_list`</nobr> | - | List active systems created via Terraform |
| <nobr>`--tf_terminate_list`</nobr> | `<list>` | Delete designated Terraform systems |
| <nobr>`--tf_terminate_all`</nobr> | - | Enter each Terraform directory and attempt to remove instance |

## Host Configuration Format

### Local Systems

For `--system_type local`, the host_config is the system name. Configuration is read from `local_configs/<hostname>.conf`:

```
server_ips: <ip1>,<ip2>
client_ips: <ip1>,<ip2>
storage: /dev/nvme2n1,/dev/nvme1n1
```

### Cloud Systems

For cloud system types, the host_config can be specified as:

#### Simple Format
```
<instance_type>[region=<val>&zone=<val>]
```

#### Extended Format
```
<instance>:<Cloud_Placement>&<CPU_type>&<Disks>&<Networks>&<Sysctl_settings>
```

**Field Definitions:**

- **instance**: Cloud instance type (e.g., `m5.xlarge`, `i3en.xlarge`)
  - Optional: `[region=<val>&zone=<val>]`
  - region: Cloud region (default: user's default region)
  - zone: Zone within region (default: randomly selected)

- **Cloud_Placement=value**: Cloud-specific placement group (default: none)

- **CPU_type=value**: String to match substring in `lscpu` Model name field

- **Disks;number=n;size=n;type=n**
  - number: How many disks to create and attach
  - size: Disk size in gigabytes
  - type: Disk type (cloud-specific, e.g., `gp2`, `io1`)

- **Networks;<system>;<system>;...;type=x**
  - system: VM type (cloud) or system name (local)
  - type: Network type
    - `default`: Default cloud network
    - `public`: Public DNS connections
    - Cloud-specific types

- **Sysctl_settings=n+n+...**: Files from `sysctl_setting` directory, separated by `+`

#### Examples

1. **Two systems, no config options:**
   ```
   m5.xlarge,m5.4xlarge
   ```

2. **System with 8 disks:**
   ```
   m5.24xlarge:Disks;number=8;size=1200;type=gp2
   ```

3. **System with sysctl tunings:**
   ```
   m5.24xlarge:Sysctl_settings=none+udp_fix
   ```

4. **System in specific region/zone:**
   ```
   "m5.xlarge[region=us-east-1&zone=b]"
   ```

5. **Two systems connected via networks:**
   ```
   m5.xlarge:Networks;m5.2xlarge
   ```

### Configuration File Format

Configuration can also be specified in a file with these fields:

```
instance_type: i3en.xlarge[region=<value>&zone=<value>]
number_networks: <n>
sysctl_settings: <file1>+<file2>
number_of_disks: <n>
disk_size: <n>
disk_type: <type>
```

## Test Override Format

The `--test_override` option allows overriding scenario file options for specific systems:

**Syntax:**
```
--test_override "system_name:option=value"
```

**Example Scenario File:**
```yaml
global:
  ssh_key_file: /home/test_user/permissions/aws_region_2_ssh_key
  terminate_cloud: 1
  cloud_os_id: aminumber
  os_vendor: rhel
  results_prefix: linpack
  system_type: aws
systems:
  system1:
    java_version: java-8
    tests: linpack
    system_type: aws
    host_config: "m5.xlarge"
  system2:
    java_version: java-8
    tests: linpack
    system_type: aws
    host_config: "m5.4xlarge"
```

**Override Example:**
```bash
--test_override "system1:java_version=java-11"
```

## Exit Behavior

burden tracks failed tests via the `failed_tests` report file. When the first invocation detects changes in failed test count, it exits with code 1.

## Operation Modes

### First Invocation (Parent Process)
- `gl_first_invocation=1`
- Performs initial setup
- Generates final test status reports
- Tracks failed tests

### Child Process
- Started with `--child` flag
- Skips initial setup work
- Does not generate final reports

## Multiple Concurrent Instances

Zathras supports running multiple instances in the same directory via:
1. Unique file names using `mktemp`
2. File locking for shared resources
   - Exclusive general lock: `gl_lock_exclusive` / `gl_unlock_exclusive`
   - Per-command locking: `flock -x <file> <command>`

## Notes

- Comment lines in scenario files start with `#`
- String replacement in scenario files: `% <current_string>=<new_string>`
- Git repository URLs should start with `https:` or `git:`
- Multiple architectures in cloud_os_id are automatically matched to designated host
