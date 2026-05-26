# Azure Terraform Templates

This directory contains Terraform templates for creating Azure virtual machines with support for both marketplace images and custom images from Azure Compute Gallery.

## Image Source Options

The templates support two types of image sources:

### 1. Marketplace Images (URN-based)
Uses Azure Marketplace images specified by publisher, offer, SKU, and version.

**Example configuration:**
```hcl
use_custom_image = false
publisher = "RedHat"
offer     = "RHEL"
sku       = "8-LVM"
azversion = "latest"
```

### 2. Custom Images (Azure Compute Gallery or Managed Images)
Uses custom images from Azure Compute Gallery or managed images specified by resource ID.

**Example configuration:**
```hcl
use_custom_image = true
az_urn_sub = "/subscriptions/xxxx/resourceGroups/yyyy/providers/Microsoft.Compute/galleries/zzzz/images/image-name/versions/1.0.0"
```

## Template Files

### Unified Templates (Recommended)
These templates automatically handle both image source types using Terraform conditional logic:

- **`vm_spot_set_unified.tf`** - VM creation without network (simplified)
- **`main_net_p2_unified.tf`** - VM creation with network configuration

The unified templates use the `use_custom_image` boolean variable to determine which image source to use:
- When `use_custom_image = true`: Uses `source_image_id` with the value from `az_urn_sub`
- When `use_custom_image = false`: Uses `source_image_reference` block with marketplace parameters

### Legacy Templates (Deprecated)
These separate templates are maintained for backward compatibility but should be replaced by unified templates:

- **URN-based (Marketplace):**
  - `vm_spot_set_urn.tf`
  - `main_net_p2_urn.tf`

- **Custom Image (Subscription):**
  - `vm_spot_set_sub.tf`
  - `main_net_p2_sub.tf`

## How It Works

### 1. Variable Definition (`vars.tf`)
```hcl
variable "use_custom_image" {
  type        = bool
  default     = false
  description = "Set to true to use custom image from Azure Compute Gallery (source_image_id), false to use marketplace image (source_image_reference)"
}
```

### 2. Conditional Image Source (in unified templates)
```hcl
# Use source_image_id for Azure Compute Gallery or managed images
source_image_id = var.use_custom_image ? var.az_urn_sub : null

# Use source_image_reference for marketplace images
dynamic "source_image_reference" {
    for_each = var.use_custom_image ? [] : [1]
    content {
        publisher = var.publisher
        offer     = var.offer
        sku       = var.sku
        version   = var.azversion
    }
}
```

### 3. Variable Setting (via Ansible)
The `use_custom_image` variable is automatically set in the tfvars template based on `cloud_os_version`:
- If `cloud_os_version == "none"` → `use_custom_image = true` (custom image)
- Otherwise → `use_custom_image = false` (marketplace image)

## Migration Notes

When migrating from legacy templates to unified templates:

1. The unified templates eliminate the need for separate template files based on image source
2. All image source logic is handled within a single template using Terraform conditionals
3. No changes required to existing variable definitions for `az_urn_sub`, `publisher`, `offer`, `sku`, or `azversion`
4. The Ansible playbook is simplified by removing conditional template selection logic

## Spot Instance Support

All templates support both regular and spot instances through placeholder replacement:
- `PRIORITYSPOT` → replaced with `priority = "Spot"` for spot instances or removed for regular instances
- `EVICTIONPOLICY` → replaced with `eviction_policy = "Deallocate"` for spot instances or removed for regular instances

## Examples

### Using Marketplace Image (RHEL 8)
```hcl
use_custom_image = false
publisher = "RedHat"
offer     = "RHEL"
sku       = "8-LVM"
azversion = "latest"
```

### Using Azure Compute Gallery Image
```hcl
use_custom_image = true
az_urn_sub = "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/myGalleryRG/providers/Microsoft.Compute/galleries/myGallery/images/myCustomImage/versions/1.0.0"
```

### Using Managed Image
```hcl
use_custom_image = true
az_urn_sub = "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/myImagesRG/providers/Microsoft.Compute/images/myManagedImage"
```
