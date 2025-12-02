# IBM Cloud Support for Zathras

This role provides IBM Cloud Virtual Server Instance (VSI) provisioning support for the Zathras test automation framework.

## Overview

The `ibm_create` role integrates IBM Cloud into Zathras, allowing users to provision VSIs for testing on IBM Cloud infrastructure. This implementation follows the same patterns as the existing AWS, Azure, and GCP cloud providers.

## ⚠️ Important: IBM Cloud Authentication

**Unlike AWS, Azure, and GCP**, IBM Cloud requires an explicit API key to be set as an environment variable for Terraform to work, even if you're logged in via `ibmcloud login`.

**You MUST export one of these environment variables before running Zathras:**
```bash
export IC_API_KEY="your-api-key"
# OR
export IBMCLOUD_API_KEY="your-api-key"
```

This is a requirement of the IBM Cloud Terraform provider and cannot be avoided.

## Prerequisites

### Required Tools

1. **IBM Cloud CLI** (`ibmcloud`)
   - Install from: https://cloud.ibm.com/docs/cli
   - Version: Latest stable release

2. **Terraform**
   - Version: >= 1.0
   - IBM Cloud provider version: ~> 1.70

3. **jq**
   - Required for JSON parsing

### IBM Cloud Setup

Before using Zathras with IBM Cloud, you must:

1. **Install and configure the IBM Cloud CLI:**
   ```bash
   # Install IBM Cloud CLI
   curl -fsSL https://clis.cloud.ibm.com/install/linux | sh

   # Login to IBM Cloud
   ibmcloud login

   # Set target region (optional, defaults to us-south)
   ibmcloud target -r us-south

   # Install VPC infrastructure plugin
   ibmcloud plugin install vpc-infrastructure
   ```

2. **Set up SSH keys in IBM Cloud:**
   ```bash
   # List existing SSH keys
   ibmcloud is keys

   # Create a new SSH key (if needed)
   ibmcloud is key-create zathras-key @~/.ssh/id_rsa.pub
   ```

3. **Create API key for Terraform:**
   ```bash
   # Create an API key
   ibmcloud iam api-key-create zathras-terraform-key -d "API key for Zathras Terraform"

   # Set as environment variable
   export IBMCLOUD_API_KEY="<your-api-key>"
   ```

4. **Set up resource group (optional):**
   ```bash
   # List resource groups
   ibmcloud resource groups

   # The role will automatically use the first available resource group
   ```

## Usage

### Basic IBM Cloud Test

```bash
./burden --system_type ibm \
         --host_config bx2-2x8 \
         --cloud_os_id r006-xxx-xxx-xxx \
         --os_vendor rhel \
         --tests linpack
```

### With Specific Region/Zone

```bash
./burden --system_type ibm \
         --host_config "bx2-2x8[region=us-east&zone=1]" \
         --cloud_os_id r006-xxx-xxx-xxx \
         --os_vendor rhel \
         --tests linpack
```

### Show Available OS Images

```bash
# Show RHEL images
./burden --system_type ibm --os_vendor rhel --show_os_versions

# Show Ubuntu images
./burden --system_type ibm --os_vendor ubuntu --show_os_versions

# Show SUSE images
./burden --system_type ibm --os_vendor suse --show_os_versions
```

### Multi-Network Test

```bash
./burden --system_type ibm \
         --host_config "bx2-4x16:Networks;number=1" \
         --cloud_os_id r006-xxx-xxx-xxx \
         --os_vendor rhel \
         --tests uperf
```

## IBM Cloud Specific Configuration

### Instance Types (Profiles)

IBM Cloud uses "profiles" for instance types. Common profiles include:

- **Balanced (bx2)**: Balanced CPU-to-memory ratio
  - `bx2-2x8`: 2 vCPUs, 8 GB RAM
  - `bx2-4x16`: 4 vCPUs, 16 GB RAM
  - `bx2-8x32`: 8 vCPUs, 32 GB RAM
  - `bx2-16x64`: 16 vCPUs, 64 GB RAM

- **Compute Optimized (cx2)**: Higher CPU-to-memory ratio
  - `cx2-2x4`: 2 vCPUs, 4 GB RAM
  - `cx2-4x8`: 4 vCPUs, 8 GB RAM

- **Memory Optimized (mx2)**: Higher memory-to-CPU ratio
  - `mx2-2x16`: 2 vCPUs, 16 GB RAM
  - `mx2-4x32`: 4 vCPUs, 32 GB RAM

View all available profiles:
```bash
ibmcloud is instance-profiles
```

### Regions and Zones

IBM Cloud regions follow the format: `<region>-<zone>` (e.g., `us-south-1`)

Available regions:
- `us-south` (Dallas)
- `us-east` (Washington DC)
- `eu-gb` (London)
- `eu-de` (Frankfurt)
- `jp-tok` (Tokyo)
- `au-syd` (Sydney)

Each region typically has 3 zones (1, 2, 3).

### OS Images

IBM Cloud uses image IDs for OS selection. Images are identified by IDs like:
- `r006-xxx-xxx-xxx` format

Use `--show_os_versions` to find available image IDs for your OS vendor.

### Network Configuration

- **Default**: Single public network interface
- **Additional Networks**: Use `Networks;number=N` in host_config
- **Network Types**: Private networks are automatically created as needed

### Resource Management

- **VPCs**: Automatically created or reused if specified
- **Security Groups**: Created with open ingress/egress for testing
- **Floating IPs**: Automatically assigned to VSIs for public access
- **SSH Keys**: Must exist in IBM Cloud before running tests

## Terraform Files

The role includes the following Terraform files:

- **main.tf**: Primary resource definitions (VPC, VSI, networking, security)
- **vars.tf**: Variable declarations
- **output.tf**: Output values (IPs, instance IDs)
- **network.tf**: Additional network configurations

## Environment Variables

The following environment variables are used:

- `IBMCLOUD_API_KEY`: IBM Cloud API key for Terraform (required)
- `IC_API_KEY`: Alternative to IBMCLOUD_API_KEY

## Configuration Variables

The role uses the following Ansible variables:

- `config_info.host_or_cloud_inst`: IBM Cloud profile (instance type)
- `config_info.cloud_os_version`: OS image ID
- `config_info.cloud_region`: IBM Cloud region
- `config_info.cloud_zone`: Zone within region
- `config_info.test_user`: SSH user (default: root)
- `config_info.ssh_key`: Path to SSH private key
- `config_info.cloud_numb_networks`: Number of additional networks

## Limitations

1. **No Spot Instance Support**: IBM Cloud doesn't have spot instances like AWS/Azure
2. **Root User Default**: Most IBM Cloud images use root as the default user
3. **SSH Key Requirement**: SSH keys must be pre-created in IBM Cloud
4. **VPC Networking**: All instances use VPC networking (no classic infrastructure)

## Troubleshooting

### API Key Issues

```bash
# Verify API key is set
echo $IBMCLOUD_API_KEY

# Test API key
ibmcloud login --apikey $IBMCLOUD_API_KEY
```

### SSH Key Not Found

```bash
# List available SSH keys
ibmcloud is keys

# Create new key if needed
ibmcloud is key-create my-key @~/.ssh/id_rsa.pub
```

### Region/Zone Issues

```bash
# Check current region
ibmcloud target

# Set specific region
ibmcloud target -r us-south

# List available zones
ibmcloud is zones us-south
```

### Image Not Found

```bash
# List available images
ibmcloud is images --visibility public

# Filter by OS
ibmcloud is images --visibility public | grep -i rhel
```

## Examples

### Scenario File Example

```yaml
global:
  system_type: ibm
  os_vendor: rhel
  results_prefix: ibm_tests

systems:
  test1:
    tests: linpack
    host_config: "bx2-4x16[region=us-south&zone=1]"
    cloud_os_id: r006-xxx-xxx-xxx
```

### Direct Command Example

```bash
# Run stream test on IBM Cloud
./burden --system_type ibm \
         --host_config bx2-8x32 \
         --cloud_os_id r006-xxx-xxx-xxx \
         --os_vendor rhel \
         --tests stream
```

## Additional Resources

- IBM Cloud Documentation: https://cloud.ibm.com/docs
- IBM Cloud VPC: https://cloud.ibm.com/docs/vpc
- IBM Cloud CLI Reference: https://cloud.ibm.com/docs/cli
- Terraform IBM Provider: https://registry.terraform.io/providers/IBM-Cloud/ibm/latest/docs

## Support

For issues specific to IBM Cloud integration in Zathras, please report at:
https://github.com/redhat-performance/zathras/issues
