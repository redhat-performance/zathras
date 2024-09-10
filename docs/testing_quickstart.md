# Testing with Zathras - Quickstart

## Testing on bare metal
- Define a scenario file
- ssh-copy-id from the SUT to the controller
- Add a local_config for the SUT
- Add SUT to the controller's known hosts


## Testing on cloud

Currently supported public clouds:
- AWS cloud
- Azure cloud
- GCP cloud

### Testing example using AWS:

We could define a scenario file, "aws_example", as follows:

    global:
        ssh_key_file: /home/user/permissions/aws_region_2_ssh_key
        terminate_cloud: 1
        cloud_os_id: ami-myaminumbe
        os_vendor: rhel
        results_prefix: linpack
        system_type: aws
    systems:
        system1:
        tests: linpack
        host_config: "m5.xlarge"


We could then begin running tests by entering in the command line:

    ./burden --scenario aws_sample


## Testing in virtualization
If the virtual machine is hosted on the controller, then the process follows the same steps as testing on bare metal.
- Define a scenario file
- ssh-copy-id from the SUT to the controller
- Add a local_config for the SUT
- Add SUT to the controller's known hosts

If the virtual machine is hosted on an external system, then you will need to create a network bridge so that Zathras can reach the SUT.
