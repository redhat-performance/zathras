# Testing with Zathras - Quickstart

## Testing on bare metal


## Testing on cloud

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
