# Testing with Zathras - Quickstart

This guide provides step-by-step instructions for getting started with Zathras testing across different environments.

## Prerequisites

Before starting, ensure you have:
1. Zathras installed on your controller system (see [Installation](../README.md#installation))
2. Test configuration files set up (see [Test Config Files](test_config_files.md))
3. Appropriate permissions and access to your target systems

## Testing on bare metal

Testing on bare metal systems requires direct SSH access to the target machines.

### Step-by-step process:

1. **Set up SSH access**
   ```bash
   # Copy your SSH key to the target system
   ssh-copy-id user@target-system-hostname
   
   # Test SSH access (should not prompt for password)
   ssh user@target-system-hostname
   ```

2. **Create a local config file**
   
   Create a file named `<hostname>.conf` in the `local_configs/` directory:
   ```bash
   # Example: local_configs/test-server.conf
   host_ip=192.168.1.100
   host_user=testuser
   host_arch=x86_64
   # Add any additional system-specific configurations
   ```

3. **Add the system to known hosts**
   ```bash
   ssh-keyscan target-system-hostname >> ~/.ssh/known_hosts
   ```

4. **Create a scenario file**
   
   Create a scenario file in your Zathras directory:
   ```yaml
   # Example: bare_metal_scenario
   global:
       results_prefix: bare_metal_test
       system_type: local
   systems:
       system1:
           tests: streams
           host_config: "test-server"
   ```

5. **Run the test**
   ```bash
   ./bin/burden --scenario bare_metal_scenario
   ```

### Example bare metal scenario

Here's a complete example for running STREAM benchmark on a bare metal system:

```yaml
global:
    results_prefix: stream_benchmark
    system_type: local
    test_iter: 3
systems:
    system1:
        tests: streams
        host_config: "production-server"
        tuned_profiles: "throughput-performance"
```

## Testing on cloud

Zathras supports automated provisioning and testing on major cloud providers.

### Currently supported clouds:
- **AWS** (Amazon Web Services)
- **Azure** (Microsoft Azure)
- **GCP** (Google Cloud Platform)

### Prerequisites for cloud testing:

1. **Cloud credentials configured** (AWS CLI, Azure CLI, or gcloud CLI)
2. **SSH key pair** for accessing cloud instances
3. **Terraform installed** (handled by Zathras installer)

### AWS Testing Example

1. **Create a scenario file**
   ```yaml
   # Example: aws_scenario
   global:
       ssh_key_file: /home/user/.ssh/aws-key
       terminate_cloud: 1
       cloud_os_id: ami-0abcdef1234567890
       os_vendor: rhel
       results_prefix: aws_linpack_test
       system_type: aws
   systems:
       system1:
           tests: linpack
           host_config: "m5.xlarge"
           java_version: java-8
   ```

2. **Run the test**
   ```bash
   ./bin/burden --scenario aws_scenario
   ```

### Azure Testing Example

```yaml
# Example: azure_scenario
global:
    ssh_key_file: /home/user/.ssh/azure-key
    terminate_cloud: 1
    cloud_os_id: /subscriptions/xxx/resourceGroups/xxx/providers/Microsoft.Compute/images/rhel-9
    os_vendor: rhel
    results_prefix: azure_fio_test
    system_type: azure
systems:
    system1:
        tests: fio
        host_config: "Standard_D4s_v3:Disks;number=2;size=1000;type=Premium_LRS"
```

### GCP Testing Example

```yaml
# Example: gcp_scenario
global:
    ssh_key_file: /home/user/.ssh/gcp-key
    terminate_cloud: 1
    cloud_os_id: projects/rhel-cloud/global/images/family/rhel-9
    os_vendor: rhel
    results_prefix: gcp_uperf_test
    system_type: gcp
systems:
    system1:
        tests: uperf
        host_config: "n2-standard-4:Networks;number=1"
```

### Multi-system cloud testing

You can test multiple systems simultaneously:

```yaml
global:
    ssh_key_file: /home/user/.ssh/aws-key
    terminate_cloud: 1
    cloud_os_id: ami-0abcdef1234567890
    os_vendor: rhel
    results_prefix: multi_system_test
    system_type: aws
systems:
    system1:
        tests: streams
        host_config: "m5.xlarge"
    system2:
        tests: fio
        host_config: "m5.2xlarge:Disks;number=4;size=2000;type=gp3"
    system3:
        host_config: "SYS_BARRIER"  # Wait for above tests to complete
    system4:
        tests: uperf
        host_config: "m5.4xlarge:Networks;number=2"
```

## Testing in virtualization

### Local VMs (hosted on controller)

If your virtual machines are running on the same system as the Zathras controller:

1. **Follow the bare metal process** - VMs are treated like any other SSH-accessible system
2. **Ensure VM networking** allows SSH access from the controller
3. **Use VM hostnames or IP addresses** in your local config files

### Remote VMs (hosted on external systems)

For VMs hosted on external hypervisors:

1. **Set up network bridging** to ensure Zathras can reach the VMs
2. **Configure port forwarding** if necessary
3. **Use accessible IP addresses** or hostnames in your configurations

### Example VM scenario

```yaml
# Example: vm_scenario
global:
    results_prefix: vm_performance_test
    system_type: local
systems:
    vm1:
        tests: coremark
        host_config: "test-vm-1"
    vm2:
        tests: streams
        host_config: "test-vm-2"
```

## Common Testing Patterns

### Running multiple test iterations

```yaml
global:
    test_iter: 5  # Run each test 5 times
    results_prefix: iteration_test
    system_type: aws
# ... rest of configuration
```

### Using different tuned profiles (RHEL only)

```yaml
systems:
    system1:
        tests: linpack
        host_config: "m5.xlarge"
        tuned_profiles: "throughput-performance,latency-performance"
        tuned_reboot: 1  # Reboot between profile changes
```

### Uploading custom RPMs

```yaml
global:
    upload_rpms: "/path/to/custom.rpm,/path/to/another.rpm"
# ... rest of configuration
```

## Troubleshooting

### Common issues and solutions:

1. **SSH connection failures**
   - Verify SSH key is properly configured
   - Check network connectivity
   - Ensure target system is accessible

2. **Cloud provisioning failures**
   - Verify cloud credentials are configured
   - Check quota limits in your cloud account
   - Ensure specified AMI/image IDs are valid

3. **Test execution failures**
   - Check test configuration files are properly set up
   - Verify required packages can be installed
   - Review Zathras logs for specific error messages

### Getting help

- Check the [command line reference](command_line_reference.md) for detailed option descriptions
- Review [scenario file documentation](scenario_files.md) for advanced configurations
- Examine [test configuration files](test_config_files.md) for test-specific settings

## Next Steps

After completing your first test runs:

1. **Review results** in the generated results directories
2. **Customize test parameters** using test-specific configurations
3. **Set up automated testing** using scenario files
4. **Explore advanced features** like multi-system testing and custom tuning profiles
