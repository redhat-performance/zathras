# Zathras CI/CD Setup Guide

This guide explains how to configure GitHub Actions CI/CD for testing Zathras across AWS, Azure, GCP, and bare metal systems.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [AWS Setup](#aws-setup)
- [Azure Setup](#azure-setup)
- [GCP Setup](#gcp-setup)
- [Bare Metal Setup](#bare-metal-setup)
- [GitHub Secrets Configuration](#github-secrets-configuration)
- [Testing the Workflows](#testing-the-workflows)
- [Troubleshooting](#troubleshooting)

## Overview

The Zathras CI pipeline consists of:

- **4 cloud-specific workflows**: AWS, Azure, GCP, and bare metal
- **Automated testing**: Triggered on PRs to main branch
- **Manual testing**: Can be triggered via GitHub Actions UI
- **OIDC authentication**: Secure, keyless authentication to cloud providers
- **Standard test suite**: Runs linpack, streams, and fio benchmarks (~15-20 min per cloud)

## Prerequisites

- GitHub repository with Actions enabled
- Admin access to configure secrets
- Cloud provider accounts (AWS, Azure, GCP)
- (Optional) Self-hosted runner for bare metal testing

## AWS Setup

### 1. Create an IAM Role for GitHub OIDC

Create an IAM role that GitHub Actions can assume using OIDC:

```bash
# 1. Create the OIDC identity provider (one-time setup)
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1

# 2. Create a trust policy file
cat > trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:YOUR_ORG/zathras:*"
        }
      }
    }
  ]
}
EOF

# Replace ACCOUNT_ID and YOUR_ORG with your values
sed -i "s/ACCOUNT_ID/$(aws sts get-caller-identity --query Account --output text)/" trust-policy.json
sed -i "s/YOUR_ORG/your-github-org/" trust-policy.json

# 3. Create the IAM role
aws iam create-role \
  --role-name GitHubActionsZathrasRole \
  --assume-role-policy-document file://trust-policy.json

# 4. Attach necessary permissions
# Create a policy with required EC2, VPC, and S3 permissions
cat > zathras-permissions.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances",
        "ec2:TerminateInstances",
        "ec2:DescribeInstances",
        "ec2:DescribeImages",
        "ec2:DescribeKeyPairs",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeSubnets",
        "ec2:DescribeVpcs",
        "ec2:CreateSecurityGroup",
        "ec2:DeleteSecurityGroup",
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:AuthorizeSecurityGroupEgress",
        "ec2:RevokeSecurityGroupIngress",
        "ec2:RevokeSecurityGroupEgress",
        "ec2:CreateTags",
        "ec2:CreateKeyPair",
        "ec2:DeleteKeyPair",
        "ec2:DescribeVolumes",
        "ec2:CreateVolume",
        "ec2:DeleteVolume",
        "ec2:AttachVolume",
        "ec2:DetachVolume"
      ],
      "Resource": "*"
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name GitHubActionsZathrasRole \
  --policy-name ZathrasTestPermissions \
  --policy-document file://zathras-permissions.json

# 5. Get the role ARN (save this for GitHub secrets)
aws iam get-role --role-name GitHubActionsZathrasRole --query 'Role.Arn' --output text
```

### 2. Create SSH Key Pair

```bash
# Generate SSH key for EC2 instances
ssh-keygen -t rsa -b 4096 -f ~/.ssh/zathras_ci_key -N ""

# The private key content will be added to GitHub secrets
cat ~/.ssh/zathras_ci_key
```

### 3. Required GitHub Secrets for AWS

Add these secrets in **Settings > Secrets and variables > Actions**:

| Secret Name | Description | Example Value |
|-------------|-------------|---------------|
| `AWS_OIDC_ROLE_ARN` | ARN of the IAM role created above | `arn:aws:iam::123456789012:role/GitHubActionsZathrasRole` |
| `AWS_SSH_PRIVATE_KEY` | Private SSH key content | Content of `~/.ssh/zathras_ci_key` |

## Azure Setup

### 1. Create Azure Service Principal with OIDC

```bash
# 1. Set variables
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
RESOURCE_GROUP="zathras-ci-rg"  # Optional: Create dedicated RG for CI
GITHUB_ORG="your-org"
GITHUB_REPO="zathras"

# 2. Create an app registration
APP_ID=$(az ad app create \
  --display-name "GitHub Actions Zathras CI" \
  --query appId -o tsv)

# 3. Create a service principal
az ad sp create --id $APP_ID

# 4. Configure federated credentials for GitHub OIDC
az ad app federated-credential create \
  --id $APP_ID \
  --parameters '{
    "name": "GitHubActionsZathras",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:'"$GITHUB_ORG"'/'"$GITHUB_REPO"':ref:refs/heads/main",
    "audiences": ["api://AzureADTokenExchange"]
  }'

# Also add credentials for PRs
az ad app federated-credential create \
  --id $APP_ID \
  --parameters '{
    "name": "GitHubActionsZathrasPR",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:'"$GITHUB_ORG"'/'"$GITHUB_REPO"':pull_request",
    "audiences": ["api://AzureADTokenExchange"]
  }'

# 5. Assign Contributor role to the service principal
az role assignment create \
  --assignee $APP_ID \
  --role Contributor \
  --scope /subscriptions/$SUBSCRIPTION_ID

# 6. Get the Tenant ID and Client ID (save for GitHub secrets)
echo "Client ID: $APP_ID"
echo "Tenant ID: $(az account show --query tenantId -o tsv)"
echo "Subscription ID: $SUBSCRIPTION_ID"
```

### 2. Create SSH Key Pair

```bash
# Generate SSH key for Azure VMs
ssh-keygen -t rsa -b 4096 -f ~/.ssh/zathras_azure_ci_key -N ""

cat ~/.ssh/zathras_azure_ci_key
```

### 3. Required GitHub Secrets for Azure

| Secret Name | Description | Example Value |
|-------------|-------------|---------------|
| `AZURE_CLIENT_ID` | Application (client) ID | `12345678-1234-1234-1234-123456789abc` |
| `AZURE_TENANT_ID` | Directory (tenant) ID | `87654321-4321-4321-4321-cba987654321` |
| `AZURE_SUBSCRIPTION_ID` | Subscription ID | `abcdef01-2345-6789-abcd-ef0123456789` |
| `AZURE_SSH_PRIVATE_KEY` | Private SSH key content | Content of `~/.ssh/zathras_azure_ci_key` |

## GCP Setup

### 1. Create Workload Identity Federation

```bash
# 1. Set variables
PROJECT_ID="your-gcp-project-id"
GITHUB_ORG="your-org"
GITHUB_REPO="zathras"
SERVICE_ACCOUNT_NAME="github-actions-zathras"

# 2. Create a service account
gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
  --display-name="GitHub Actions Zathras CI" \
  --project=$PROJECT_ID

# 3. Grant necessary permissions to the service account
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/compute.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

# 4. Create Workload Identity Pool
gcloud iam workload-identity-pools create "github-actions-pool" \
  --project=$PROJECT_ID \
  --location="global" \
  --display-name="GitHub Actions Pool"

# 5. Create Workload Identity Provider
gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --project=$PROJECT_ID \
  --location="global" \
  --workload-identity-pool="github-actions-pool" \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# 6. Allow the GitHub repo to impersonate the service account
gcloud iam service-accounts add-iam-policy-binding \
  "${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --project=$PROJECT_ID \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')/locations/global/workloadIdentityPools/github-actions-pool/attribute.repository/${GITHUB_ORG}/${GITHUB_REPO}"

# 7. Get the Workload Identity Provider resource name (save for GitHub secrets)
echo "Workload Identity Provider:"
gcloud iam workload-identity-pools providers describe "github-provider" \
  --project=$PROJECT_ID \
  --location="global" \
  --workload-identity-pool="github-actions-pool" \
  --format="value(name)"

echo ""
echo "Service Account:"
echo "${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
```

### 2. Create SSH Key Pair

```bash
# Generate SSH key for GCP instances
ssh-keygen -t rsa -b 4096 -f ~/.ssh/zathras_gcp_ci_key -N ""

cat ~/.ssh/zathras_gcp_ci_key
```

### 3. Required GitHub Secrets for GCP

| Secret Name | Description | Example Value |
|-------------|-------------|---------------|
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Workload Identity Provider resource name | `projects/123456789/locations/global/workloadIdentityPools/github-actions-pool/providers/github-provider` |
| `GCP_SERVICE_ACCOUNT` | Service account email | `github-actions-zathras@your-project.iam.gserviceaccount.com` |
| `GCP_PROJECT_ID` | GCP Project ID | `your-gcp-project-id` |
| `GCP_SSH_PRIVATE_KEY` | Private SSH key content | Content of `~/.ssh/zathras_gcp_ci_key` |

## Bare Metal Setup

Bare metal testing requires a self-hosted GitHub Actions runner.

### 1. Set Up Self-Hosted Runner

Follow [GitHub's documentation](https://docs.github.com/en/actions/hosting-your-own-runners/adding-self-hosted-runners) to add a self-hosted runner.

**Recommended configuration:**
- **Labels**: `self-hosted`, `linux`, `baremetal`
- **Runner name**: Something descriptive like `baremetal-ci-runner`

### 2. Install Dependencies on Runner

```bash
# On the self-hosted runner machine, run Zathras installation
cd /path/to/zathras
sudo ./bin/install.sh
```

### 3. Configure SSH Access

The runner needs passwordless SSH access to target bare metal systems:

```bash
# On the runner machine
ssh-keygen -t rsa -b 4096 -f ~/.ssh/zathras_baremetal_key -N ""

# Copy public key to target systems
ssh-copy-id -i ~/.ssh/zathras_baremetal_key user@target-host
```

### 4. Create Local Config Files

Create local config files for each bare metal system in `local_configs/`:

```bash
# Example: local_configs/baremetal-test-01.config
cat > local_configs/baremetal-test-01.config << 'EOF'
# Bare metal test system configuration
hostname=baremetal-test-01
ip_address=192.168.1.100
ssh_user=root
# Add other system-specific configuration
EOF
```

### 5. Required GitHub Secrets for Bare Metal

| Secret Name | Description | Example Value |
|-------------|-------------|---------------|
| `BAREMETAL_SSH_PRIVATE_KEY` | (Optional) SSH private key if not using runner's default | Content of SSH private key |

## GitHub Secrets Configuration

### Adding Secrets to GitHub

1. Go to your repository on GitHub
2. Navigate to **Settings > Secrets and variables > Actions**
3. Click **New repository secret**
4. Add each secret listed above with its corresponding value

### Secret Summary

Here's a complete list of all secrets needed:

**AWS:**
- `AWS_OIDC_ROLE_ARN`
- `AWS_SSH_PRIVATE_KEY`

**Azure:**
- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_SSH_PRIVATE_KEY`

**GCP:**
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT`
- `GCP_PROJECT_ID`
- `GCP_SSH_PRIVATE_KEY`

**Bare Metal:**
- `BAREMETAL_SSH_PRIVATE_KEY` (optional)

## Testing the Workflows

### Manual Testing

1. Go to **Actions** tab in your GitHub repository
2. Select one of the workflows (e.g., "Test AWS")
3. Click **Run workflow**
4. Fill in any required inputs (or use defaults)
5. Click **Run workflow** button
6. Monitor the workflow execution

### Automatic Testing (PRs)

When you create a pull request that modifies relevant files, the workflows will automatically run.

**Monitored paths:**
- `bin/**` - Zathras core scripts
- `ansible_roles/**` - Ansible roles
- `config/**` - Configuration files
- `ci/test_scenarios/*.yml` - Test scenarios
- `.github/workflows/*.yml` - Workflow definitions
- `.github/actions/**` - Composite actions

### Expected Results

Each workflow should:
1. ✅ Authenticate to the cloud provider (or verify SSH for bare metal)
2. ✅ Set up Zathras and dependencies
3. ✅ Provision cloud resources (or connect to bare metal)
4. ✅ Run test suite (linpack, streams, fio)
5. ✅ Validate results
6. ✅ Clean up resources
7. ✅ Upload test results as artifacts
8. ✅ Post results comment on PR (if triggered by PR)

**Total runtime:** ~15-20 minutes per cloud provider

## Troubleshooting

### AWS Issues

**Problem:** `An error occurred (UnauthorizedOperation) when calling the RunInstances operation`

**Solution:** Check that the IAM role has the required EC2 permissions listed in the setup section.

---

**Problem:** `Unable to locate credentials`

**Solution:** Verify that `AWS_OIDC_ROLE_ARN` secret is set correctly and the trust policy allows your repository.

### Azure Issues

**Problem:** `AADSTS70021: No matching federated identity record found`

**Solution:** Ensure federated credentials are created for both `ref:refs/heads/main` and `pull_request` subjects.

---

**Problem:** `Authorization failed`

**Solution:** Verify the service principal has Contributor role on the subscription.

### GCP Issues

**Problem:** `Failed to impersonate service account`

**Solution:** Check that the Workload Identity Pool allows your repository and the service account has `roles/iam.workloadIdentityUser`.

---

**Problem:** `Permission denied (compute.instances.create)`

**Solution:** Ensure the service account has `roles/compute.admin` role.

### Bare Metal Issues

**Problem:** `No runner available`

**Solution:** Ensure a self-hosted runner with the `baremetal` label is online and idle.

---

**Problem:** `SSH connection failed`

**Solution:** Verify SSH keys are configured correctly and the runner can reach the target host.

---

**Problem:** `Local config file not found`

**Solution:** Create a local config file in `local_configs/<hostname>.config`.

### General Issues

**Problem:** Tests timing out

**Solution:** Increase the `timeout-minutes` value in the workflow file or optimize test parameters in scenario files.

---

**Problem:** Results not uploaded

**Solution:** Check that the results directory exists and contains files. The workflow will upload artifacts even on failure.

---

**Problem:** Resources not cleaned up

**Solution:** Check the "Check for orphaned resources" step in workflow logs. Manually clean up using cloud provider console.

## Cost Optimization

To minimize CI costs:

1. **Use spot/preemptible instances**: Already configured in test scenarios
2. **Limit concurrent workflows**: Configure workflow concurrency in `.github/workflows/`
3. **Manual triggers**: Use `workflow_dispatch` for expensive tests
4. **Smaller instances**: Adjust `host_config` in scenario files for cheaper instance types
5. **Shorter tests**: Reduce benchmark run times in scenario files
6. **Scheduled cleanup**: Set up scheduled workflows to scan for orphaned resources

## Next Steps

- [ ] Configure all cloud provider OIDC integrations
- [ ] Add GitHub secrets
- [ ] Test each workflow manually
- [ ] Set up self-hosted runner for bare metal (if needed)
- [ ] Monitor first automated PR runs
- [ ] Adjust timeout values and test parameters as needed
- [ ] Set up cost monitoring alerts in cloud providers

## Support

For issues or questions:
- Check workflow logs in GitHub Actions
- Review this documentation
- Open an issue in the repository
- Consult cloud provider documentation for OIDC setup

---

**Last updated:** 2025-12-09
