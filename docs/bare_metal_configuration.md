# Bare Metal Configuration

When testing on bare metal systems, Zathras requires local configuration files to specify system-specific information such as network interfaces and storage devices. This guide explains how to create and configure these files.

## Overview

For bare metal testing, Zathras uses the `system_type: local` configuration and requires:

1. **SSH access** - Passwordless SSH access from the controller to the target system
2. **Local configuration file** - A system-specific configuration file in the `local_configs/` directory
3. **Hostname resolution** - The target system must be reachable by hostname or IP

## Local Configuration Files

### File Location and Naming

Local configuration files must be placed in the `local_configs/` directory of your Zathras installation and follow this naming convention:

```
local_configs/<hostname>.config
```

Where `<hostname>` matches the `host_config` value specified in your scenario file.

### Configuration File Format

The configuration file uses a simple `key: value` format with comma-separated lists for multiple values.

#### Required Fields

**storage**: Specifies storage devices for tests that require disk I/O
```
storage: /dev/nvme0n1,/dev/nvme1n1,/dev/sdb,/dev/sdc
```

**server_ips**: Network interfaces or IP addresses for server-side network tests
```
server_ips: 192.168.1.100,10.0.0.50
```

**client_ips**: Network interfaces or IP addresses for client-side network tests  
```
client_ips: 192.168.1.101,10.0.0.51
```

### Field Usage by Test Type

Different tests require different configuration fields:

- **Storage tests** (fio, iozone, etc.): Require `storage` field
- **Network tests** (uperf): Require `server_ips` and `client_ips` fields
- **CPU/Memory tests** (linpack, streams, coremark): No local config required

### Example Configuration Files

#### Example 1: System with NVMe storage
```
# local_configs/production-server.config
storage: /dev/nvme0n1,/dev/nvme1n1
server_ips: 192.168.100.10
client_ips: 192.168.100.11
```

#### Example 2: System with SATA drives and multiple networks
```
# local_configs/test-machine.config  
storage: /dev/sdb,/dev/sdc,/dev/sdd,/dev/sde
server_ips: 10.0.1.100,192.168.1.100
client_ips: 10.0.1.101,192.168.1.101
```

#### Example 3: CPU-only testing (no storage/network tests)
```
# local_configs/cpu-test-box.config
# No fields required for CPU-only tests like linpack, streams, coremark
# This file can be empty or contain comments only
```

## Setting Up Bare Metal Testing

### Step 1: Configure SSH Access

Ensure passwordless SSH access from your Zathras controller to the target system:

```bash
# Generate SSH key if you don't have one
ssh-keygen -t rsa -b 4096

# Copy your SSH key to the target system
ssh-copy-id root@target-hostname

# Test SSH access (should not prompt for password)
ssh root@target-hostname
```

### Step 2: Create Local Configuration File

Create a configuration file for your target system:

```bash
# Create the local config file
cat > local_configs/my-server.config << EOF
storage: /dev/nvme0n1,/dev/nvme1n1
server_ips: 192.168.1.100
client_ips: 192.168.1.101
EOF
```

### Step 3: Create Scenario File

Create a scenario file that references your local configuration:

```yaml
# bare_metal_scenario.yml
global:
    results_prefix: bare_metal_test
    system_type: local
systems:
    system1:
        tests: fio
        host_config: "my-server"  # Matches local_configs/my-server.config
```

### Step 4: Run Tests

Execute your tests:

```bash
./bin/burden --scenario bare_metal_scenario.yml
```

## Troubleshooting

### Common Issues

**Error: "local_configs/hostname.config does not exist"**
- Ensure the config file exists and the filename matches your `host_config` value
- Check that the file has the `.config` extension

**Error: "No storage entry in local_configs/hostname.config"**
- Add a `storage:` line to your config file for storage-intensive tests
- Ensure storage devices are not currently mounted or in use

**Error: "No server_ips entry in local_configs/hostname.config"**
- Add `server_ips:` and `client_ips:` lines for network tests
- Verify IP addresses or hostnames are reachable

**SSH connection failures**
- Verify passwordless SSH access: `ssh root@target-hostname`
- Check that the target system is in your SSH known_hosts file
- Ensure the target hostname resolves correctly

### Validation

To verify your configuration before running tests:

```bash
# Check if your config file exists
ls -la local_configs/your-hostname.config

# Validate SSH access
ssh root@your-hostname "echo 'SSH access working'"

# Check storage devices exist
ssh root@your-hostname "ls -la /dev/nvme* /dev/sd*"

# Test network connectivity
ping your-server-ip
ping your-client-ip
```

## Advanced Configuration

### Using Device Names vs. Device Paths

You can specify storage devices using either device paths or device names:

```bash
# Using device paths (recommended)
storage: /dev/nvme0n1,/dev/nvme1n1

# Using device names (less reliable)
storage: nvme0n1,nvme1n1
```

### Network Interface Specification

For network tests, you can specify:

```bash
# IP addresses
server_ips: 192.168.1.100,10.0.0.100
client_ips: 192.168.1.101,10.0.0.101

# Hostnames (must be resolvable)
server_ips: server1.example.com,server1-ib.example.com
client_ips: client1.example.com,client1-ib.example.com
```

### Multiple System Configuration

For scenarios involving multiple bare metal systems:

```yaml
global:
    results_prefix: multi_system_test
    system_type: local
systems:
    system1:
        tests: uperf
        host_config: "server1"     # Uses local_configs/server1.config
    system2:
        tests: fio  
        host_config: "server2"     # Uses local_configs/server2.config
```

Each system requires its own configuration file in the `local_configs/` directory.
