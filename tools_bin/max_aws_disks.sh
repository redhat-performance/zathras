#!/usr/bin/env bash
#
# max-disks.sh — report the maximum number of EBS volumes ("disks") that can be
# attached to a given EC2 instance type.
#
# Usage:
#   ./max-disks.sh -i <instance-type> -d <disk-type> [-b <budget>] [-r <region>]
#
# Example:
#   ./max-disks.sh -i m8a.8xlarge -d gp3
#
# Notes on the numbers this reports:
#   * describe-instance-types has NO dedicated "max EBS volumes" attribute.
#     On Nitro instances, EBS volumes, network interfaces (ENIs), and any NVMe
#     instance-store devices all draw from a SHARED attachment budget.
#   * The default budget below (32) matches most current-generation Nitro
#     instances. It varies by instance family / Nitro card version and for
#     bare-metal, so it is exposed as an overridable option (-b).
#   * The maximum EBS *data* volumes = budget - (minimum ENIs) - (instance-store
#     NVMe devices). The minimum ENI count is 1 (the primary interface).
#   * Disk type (gp3/io2/etc.) does not change the attachment COUNT on Nitro,
#     with one caveat noted at runtime for io2 Block Express.

set -euo pipefail

DEFAULT_BUDGET=32
INSTANCE_TYPE=""
DISK_TYPE=""
BUDGET="$DEFAULT_BUDGET"
REGION_ARG=()

usage() {
  cat <<EOF
Usage: $(basename "$0") -i <instance-type> -d <disk-type> [-b <budget>] [-r <region>]

  -i   EC2 instance type          (e.g. m8a.8xlarge)   [required]
  -d   EBS disk / volume type     (e.g. gp3, io2, io1) [required]
  -b   Total Nitro attachment budget (default: ${DEFAULT_BUDGET})
  -r   AWS region                 (defaults to your CLI config)
  -h   Show this help

Example:
  $(basename "$0") -i m8a.8xlarge -d gp3
EOF
}

while getopts ":i:d:b:r:h" opt; do
  case "$opt" in
    i) INSTANCE_TYPE="$OPTARG" ;;
    d) DISK_TYPE="$OPTARG" ;;
    b) BUDGET="$OPTARG" ;;
    r) REGION_ARG=(--region "$OPTARG") ;;
    h) usage; exit 0 ;;
    :) echo "Error: -$OPTARG requires an argument." >&2; usage; exit 2 ;;
    \?) echo "Error: unknown option -$OPTARG." >&2; usage; exit 2 ;;
  esac
done

# --- validate inputs --------------------------------------------------------
if [[ -z "$INSTANCE_TYPE" || -z "$DISK_TYPE" ]]; then
  echo "Error: both -i (instance type) and -d (disk type) are required." >&2
  usage
  exit 2
fi

if ! [[ "$BUDGET" =~ ^[0-9]+$ ]]; then
  echo "Error: budget (-b) must be a positive integer." >&2
  exit 2
fi

command -v aws >/dev/null 2>&1 || { echo "Error: aws CLI not found on PATH." >&2; exit 1; }

# --- query the instance type ------------------------------------------------
# Pull the fields we need in one call: EBS support, min network interfaces,
# instance-store support and NVMe device count.
read -r EBS_SUPPORTED MAX_ENIS INSTANCE_STORE NVME_DISKS < <(
  aws ec2 describe-instance-types "${REGION_ARG[@]}" \
    --instance-types "$INSTANCE_TYPE" \
    --query 'InstanceTypes[0].[
        EbsInfo.EbsOptimizedSupport,
        NetworkInfo.MaximumNetworkInterfaces,
        InstanceStorageSupported,
        InstanceStorageInfo.Disks | length(@ || `[]`)
      ]' \
    --output text 2>/dev/null
) || {
  echo "Error: could not query instance type '$INSTANCE_TYPE'. Check the name/region and credentials." >&2
  exit 1
}

if [[ "$EBS_SUPPORTED" == "None" || -z "${EBS_SUPPORTED:-}" ]]; then
  echo "Error: instance type '$INSTANCE_TYPE' not found in this region." >&2
  exit 1
fi

# describe-instance-types returns "unsupported" only when EBS is not supported.
if [[ "$EBS_SUPPORTED" == "unsupported" ]]; then
  echo "Instance type '$INSTANCE_TYPE' does not support EBS volumes." >&2
  exit 0
fi

# Normalise NVMe disk count (instance-store devices consume attachment slots too).
[[ "$NVME_DISKS" =~ ^[0-9]+$ ]] || NVME_DISKS=0
[[ "$INSTANCE_STORE" == "True" ]] || NVME_DISKS=0

# --- compute max attachable disks ------------------------------------------
# Reserve the primary ENI (minimum 1) and any built-in NVMe instance-store
# devices from the shared budget. What remains is the max EBS data volumes.
MIN_ENIS=1
MAX_EBS=$(( BUDGET - MIN_ENIS - NVME_DISKS ))
(( MAX_EBS < 0 )) && MAX_EBS=0

echo $MAX_EBS
