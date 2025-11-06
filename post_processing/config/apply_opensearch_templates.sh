#!/bin/bash
#
# Apply OpenSearch index templates with increased field limits and nested validation
#
# Usage: ./apply_opensearch_templates.sh <opensearch_url> <username> <password>
#
# Example:
#   ./apply_opensearch_templates.sh https://opensearch.app.intlab.redhat.com automotive 'D6O8#zke0iSc'
#
# Note: Templates only apply to NEW indices. To apply to existing indices, you must delete them first.
#

set -e

if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <opensearch_url> <username> <password>"
    echo ""
    echo "Example:"
    echo "  $0 https://opensearch.app.intlab.redhat.com automotive 'password'"
    exit 1
fi

OPENSEARCH_URL="$1"
USERNAME="$2"
PASSWORD="$3"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================"
echo "Applying OpenSearch Templates"
echo "========================================"
echo ""

# Apply results template
echo "1. Applying zathras-results template..."
curl -k -X PUT "${OPENSEARCH_URL}/_index_template/zathras-results-template" \
  -u "${USERNAME}:${PASSWORD}" \
  -H 'Content-Type: application/json' \
  -d @"${SCRIPT_DIR}/opensearch_index_template.json"
echo ""
echo ""

# Apply timeseries template
echo "2. Applying zathras-timeseries template..."
curl -k -X PUT "${OPENSEARCH_URL}/_index_template/zathras-timeseries-template" \
  -u "${USERNAME}:${PASSWORD}" \
  -H 'Content-Type: application/json' \
  -d @"${SCRIPT_DIR}/opensearch_timeseries_template.json"
echo ""
echo ""

echo "========================================"
echo "Verification"
echo "========================================"
echo ""

# Verify templates are applied
echo "3. Verifying templates..."
echo ""
echo "Results template:"
curl -k -s -X GET "${OPENSEARCH_URL}/_index_template/zathras-results-template" \
  -u "${USERNAME}:${PASSWORD}" | python3 -m json.tool | grep -A 5 "total_fields"
echo ""
echo "Timeseries template:"
curl -k -s -X GET "${OPENSEARCH_URL}/_index_template/zathras-timeseries-template" \
  -u "${USERNAME}:${PASSWORD}" | python3 -m json.tool | grep -A 5 "total_fields"
echo ""

echo "========================================"
echo "Done!"
echo "========================================"
echo ""
echo "Templates applied successfully!"
echo ""
echo "Note: Templates only apply to NEW indices."
echo "To apply templates to existing indices, you must delete and recreate them:"
echo "  curl -k -X DELETE '${OPENSEARCH_URL}/zathras-results' -u '${USERNAME}:PASSWORD'"
echo "  curl -k -X DELETE '${OPENSEARCH_URL}/zathras-timeseries' -u '${USERNAME}:PASSWORD'"
echo ""

