# Test configuration files
The test configuration file is used to define a given test to Zathras, and specifies test options to use.

Test config files are stored within the `config/` directory of your Zathras installation.

## Test config file contents
The following shows all the possible options a test configuration file could contain (fields are explained below). In practice, a test config file does not require every field be included. 

    test_defs:
        test:
        test_template: 
        test_name: 
        test_description: 
        repository_type: 
        location: 
        reboot_system: "yes/no"
        test_run_from: "local/remote"
        repo_file: 
        version: 
        test_grouping: 
        os_supported: 
        rhel_pkgs: 
        ubuntu_pkgs: 
        amazon_pkgs: 
        pbench_required: 
        pbench_local_results: 
        storage_required: 
        network_required: 
        java_required: 
        archive_results: 
        test_script_to_run: 
        test_specific: 
        upload_extra: 

## Field definitions
test<n>: is a unique numerical value from the other tests. Other than for creation of the yml file, it has no bearing on the test execution.

test_template: Is a pointer to a specific test template that will be brought in. Purpose is that when we need to make changes for a specifc test, we update the test_template file not the test_defs.yml.

test_name: designates the name that zathras knows the test by. This name is what is passed in with the --tests option.

test_description: A brief description of what the test does. This information is displayed when the --show_tests option is provided to burden.

repository_type: The type of repository that the test is located in. Valid values include:

    git_tar: Mainly used when pulling an entire git repository for a test.

    git_file: Designated when pulling a single file from a git repository.

    git_tag: Will pull based on the git_tag.

    file: Indicates we are copying a file.

    tar: Indicates we are copying a tarball.

location: Is the location at which the test can be found. Note in the case of git, it will be everything minus the actual location name. For example, if we have:

    https://github.com/redhat-performance/streams-wrapper/

We will drop the streams-wrapper on the end and have

    https://github.com/redhat-performance/



version: The version of the test to use. For a listing of versions available, you can issue the following command:

    $ ./burden --test_versions streams
    ============================
    streams
    ============================
    v1.0            Merge pull request #2 from redhat-performance/fix_usage



test_grouping : Is the grouping name of the tests. In the case of a git repo, it will be the actual location name. For example, if we have:

    https://github.com/redhat-performance/streams-wrapper/

we drop everything but streams-wrapper and use "streams-wrapper"

os_supported: What Operating Systems are supported. rhel, ubuntu, amazon or all.

reboot_system: This is for cloud systems, and will reboot the cloud system once it has been created.

test_run_from: Some tests need to run from the local system, not the cloud system (boot timing test is one example). If local is specified, the test will run locally, if remote is specified the test will run on the test system.

repo_file: The archive file to be downloaded. In the case of git repos, it will be <tag>.zip

rhel_pkgs: RHEL packages that are required to run the test; “none” if there aren’t any packaging requirements

ubuntu_pkgs: Ubuntu packages that are required to run the test; “none” if there aren’t any packaging requirements.

amazon_pkgs: Amazon packages that are required to run the test; “none” if there aren’t any packaging requirements.

pbench_required: If set to yes, the test requires pbench to be installed to run. Zathras will install pbench on the test system for you. Only supported for RHEL/Fedora. Note: it is the responsibility of the user to make sure the pbench repos are set up properly.

pbench_local_result: If set to yes, will tell the various wrapper scripts to consolidate the pbench results into a results tarball in /tmp with the format:

    results_<workload>_<tuned_setting>.tar
e.g.
    
    results_pbench_linpack_tuned_virtual-guest_sys_file_none.tar

storage_required: If set to yes, Zathras will check to make sure storage has been designated for the system before provisioning it.

network_required: If set to yes, Zathras will check to make sure a network (other than the defaults) has been designated for the system before provisioning it.

java_required: If set to yes, Zathras will make sure that a Java Version has been provided before provisioning any system.

archive_results: Tell zathras that it has test results to retrieve from the test system.

test_script_to_run: The script that Zathras is to run.

test_specific: Test options that are specific to the test.

upload_extra: If not set to “none”, uploads the each file in the comma separated list to the test system.

## Example

    test3:
        test_name: streams
        exec_dir: "streams-wrapper-1.0/streams"
        location: https://github.com/redhat-performance/streams-wrapper/archive/refs/tags
        reboot_system: "no"
        test_run_from: "remote"
        os_supported: all
        repo_file: "v1.0.zip"
        rhel_pkgs: gcc,bc
        ubuntu_pkgs: gcc,build-essential,libnuma-dev,zip,unzip
        amazon_pkgs: gcc,bc,git,unzip,zip
        pbench_required: "no"
        pbench_local_results: "no"
        storage_required: "no"
        network_required: "no"
        java_required: "no"
        archive_results: "yes"
        test_script_to_run: streams_run
        test_specific: ""
        upload_extra: "none"
        post_script: "none"
        pre_setup: "none"