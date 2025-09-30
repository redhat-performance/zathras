# Command line interface (CLI) reference

## Usage

    ./bin/burden <options> [<args>...]

## Options

### --archive \<dir>/\<results>
Sets the location where the archive information will be saved.

### --child
Tells burden it is a child of another burden process and not to perform the initial setup work.

### --create_attempts
Number of times we attempt to create an instance to get the desginated cpu type.

### --git_timeout
Number of seconds to timeout on git requests. Default is 60.

### --system_type \<vendor>
aws, azure, gcp or local.

### --host_config \<config options>
Specification of the system and configuration. Possible values are "cloud" and "local".

If the --system_type option is local, then this is simply the system name to run on, and it will pull the config value from the file <hostname>.conf in the local_configs directory. For more information on local_configs, please see the [local_configs README](../local_configs/README). 

If the --system_type option is cloud, then the following fields may be specified in the config file:
- instance type: The cloud instance (ie i3en.xlarge). Inclusion of \[region=\<value>&zone=\<value>] is optional.
- region: The region where the cloud is created. The default option is the user's default region.
- zone: The zone within the region the cloud will be created in. Randomly chosen by default.

### --ignore_repo_errors
If present we will ignore repo errors, default is to abort the run when a repo error occurs.

### --individ_vars
Contains various burden settings. Takes precedence over the scenario file, but is overridden by the command line. Default is config zathras_specific_vals_def.

### --java_version
Java version to install: java-8, java-11, java-17, or java-21.

### --kit_upload_directory
Full path to directory uploading to. If not present, Zathras will locate the filesystem with the most space on it and use that location.

### --max_systems \<n>
Maximum number of burden subinstances that will be created from the parent. Each subinstance is a cloud or local system. 3 is the default.

### --no_clean_up
Do not cleanup at the end of the test.

### --no_packages
Do not install any packages, default is no.

### --no_pbench_install
Do not install pbench. The default is 0 (install pbench).

### --no_spot_recover
Do not recover from a spot system going away.

### --os_vendor \<os vendor>
Currently rhel, ubuntu, amazon, suse.

### --package_name \<name>
Use this set of packages to override the default in the test config file instead of the default. Default format package name \<os>_pkg, new name \<os>_pkg_\<ver>.

### --persistent_log
Enable persistent logging.

### --preflight_check
Performs various checks on the scenario file, and Zathras and then exits.

### --results_prefix \<prefix>
Run directory prefix

### --retry_failed_tests \<0/1>
Indicates to retry any detected failed tests if set to 1 (1 is the default).

### --scenario \<scenario definition file>
Reads in a scenario and then runs it (if used, host configs are designated in the file). 

If the scenario name starts with https: or git:, then the scenario file is retrieved from a git repo. 

If the line in the scenario file starts with #, then that line is a comment. 

If the line starts with a %, it indicates to replace the string.

Format to replace a string % \<current string>=\<new string>
 
### --scenario_vars <file>
File that contains the variables for the scenario file, default is config/zathras_scenario_vars_def.
 
### --selinux_level
enforcing/permissive/disabled. The setting to have in /etc/selinux/config file. Note: Zathras does not support enforcing in Ubuntu at this time.

### --selinux_state 
disabled/enabled. If disabled is selected, selinux will be disabled via grubby (Amazon and RHEL). For Ubuntu,
enabled will install the require packages, update the config file and reboot.
 
### --ssh_key_file
Designates the ssh key file we are to use.
 
### --show_os_versions
Given the cloud type and OS vendor, show the available operating system versions.

### --show_tests
List the available test as defined in config/test_defs.yml

### --test_def_file \<file>
Test definition file to use.
 
### --test_def_dir \<dir>
Test definition directory. Default is \<execution dir>/config. If https: or git: is at the start of the location, then we will pull from a git repo.

### --test_override \<options>
Overrides the given options for a specific test in the scenario file.

### --tests \<test>
testname, you may use "test1,test2" to execute test1 and test2.

### --test_iter \<iterations>
How many iterations of the test to run (includes linpack).
For cloud instances, this will terminate the cloud image and start a new image for each iteration.

### --test_versions \<test>,\<test>....
Shows the versions of the test the are available and brief description of the version. This only applies to git repos

### --test_version_check
Checks to see if we are running the latest versions of the tests and exits out when done. Default is no.

### --tf_list
List active systems created via tf (terraform?).

### --tf_terminate_list
Delete the designated terraform systems.

### --tf_terminate_all
Go into each terraform directory and attempt to remove the terraform instance.

### --tuned_profiles \<comma separated list of tuned profiles>
Note: only for RHEL. Designates the tuned profiles to use. if the system type is a cloud environment, then each tuned profile is a distinct cloud instance.

### --tuned_reboot \<>
Note: only for RHEL. If value is 1 we will reboot the system each time a new tuned profile is set.

### --verbose
Verbose usage message.

### --upload_rpms ,....
Comma separated list of rpms (full path) to upload and install.

### --update_target
Image to update.

Note: only 1 update image can be used, makes no difference if designate a different one for each system in the scenario file, the first one will be used.

### --use_latest_version
Will update the templates so we are using the latest versions of the test (git repos only).

### -h --usage
Condensed usage information.

## Cloud-only options

## --cloud_os_id \<os id>
Image of the OS to install (example aws aminumber)
For multiple architectures, this is allowed"
x86:ami-0fbec8a0a2beb6a71,arm64:ami-0cfa90ca3ebfc506e"
Burden will select the right ami for the designated host."

### --create_only
Only do the VM creation and OS install action.

### --terminate_cloud
If 1, terminate the cloud instance, if 0 leave the cloud image running. Default is to terminate.

### --use_spot
Uses spot pricing based on the contents of config/spot_price.cfg. Default is not to use spot_pricing

### --ansible_noise_level \<level>
How much information ansible is to output. Options: normal (standard ansible output), dense (just report the task executed), silence (nothing reported).

### --force_upload
Force upload of files even if they already exist on the target system.

### --mode \<mode>
Operating mode. Use 'image' for bootc-based hosts (skips packages, uses safe upload paths).

### --test_user \<user>
Name of the user to log into the system with. This setting will override the defaults based on cloud or local system.

### --update_test_versions
Will update the templates so we are using the latest versions of the test (git repos only).