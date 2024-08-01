# Scenario files
Using a scenario file to configure tests offers several advantages over setting the parameters via the command line. Scenario files provide more flexibility in defining tests, greater ease of modifying tests, improved test reproducibility, and enable the creation of more complex test runs. Once a scenario file is created, that scenario can also easily be exported for future use.

## Scenario file format

    global:
        <global options>
    systems:
        system1:
            <system1 options>

The outline above can also easily be extended to incorporate multiple systems within a single scenario, like so:

    global:
        <global options>
    systems:
        system1:
            <system1 options>
        system2:
            <system2 options>

## Scenario file options
The options in the parameters file maps directly back to the CLI options, minus the dash.


## Using scenario files

Scenario files are placed within your Zathras working directory, and can be given any name. For example, given a scenario file `my_scenario`, the following command would begin a Zathras run using that scenario file:

    ./bin/burden --scenario my_scenario

## Examples

### Scenario file for bare metal
Example 1: This scenario would run the STREAM benchmark on a local bare metal system named "test_sys".

    global:
        result_prefix: just_a_test
        system_type: local
    systems:
        system1:
            tests: streams
            host_config: "test_sys"

### Scenario files for cloud
Example 2: Create an AWS system, list system information, then delete the instance.
  
    global:
        ssh_key_file: replace_your_ssh_key
        terminate_cloud: 0
        os_vendor: rhel
        results_prefix: create_only
        os_vendor: rhel
        system_type: aws
    systems:
        system1:
            cloud_os_id: ami-078cbc4c2d057c244
            host_config: "m6a.xlarge"

Example 3: This scenario would run a test on public cloud using AWS with two hosts, "m5.xlarge" and "m5.12xlarge".

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

Run fio on AWS m5.xlarge (2 disks) and m5.12xlarge (4 disks); disks are 6TB, and type is gp2:

    global:
        ssh_key_file: /home/test_user/permissions/aws_region_2_ssh_key
        terminate_cloud: 1
        cloud_os_id: ami-0fdea47967124a409
        os_vendor: rhel
        results_prefix: just_a_test
        system_type: aws
    systems:
        system1:
        tests: fio
            host_config: "m5.xlarge:Disks;number=2;size=6000;type=gp2,m12.xlarge:Disks;number=4;size=6000;type=gp2

Run fio on AWS m5.xlarge with 2 disks, and then run uperf on AWS m5.xlarge, 1 network. Note the SYS_BARRIER that indicates we will pause at that point, wait for all tests to finish, and then start the next batch. The m5.xlarge created for fio will be terminated at the end of the fio run and a new m5.xlarge for the uperf run will be created: