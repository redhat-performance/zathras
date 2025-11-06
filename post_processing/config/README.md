# Post-Processing Configuration

This directory contains configuration files for the Zathras post-processing pipeline.

## Files

### `opensearch_index_template.json`
OpenSearch index template for the `zathras-results` index (summary documents).

**Features:**
- Field limit: **5,000** (increased from default 1,000)
- Dynamic templates for runs (`run_1`, `run_2`, etc.)
- Object mappings for NUMA nodes, storage devices, network interfaces
- Boolean object for CPU flags
- Optimized for high-core systems (64+ cores)

**Usage:**
Apply using curl (requires admin permissions):
```bash
curl -k -X PUT "https://opensearch.example.com/_index_template/zathras-results-template" \
  -u "admin:password" -H 'Content-Type: application/json' \
  -d @opensearch_index_template.json
```

### `opensearch_timeseries_template.json`
OpenSearch index template for the `zathras-timeseries` index (individual time series points).

**Features:**
- Field limit: **2,000**
- Optimized for high-volume time series data
- Minimal field set per document
- Full SUT context denormalized into each point

**Usage:**
Apply using curl (requires admin permissions):
```bash
curl -k -X PUT "https://opensearch.example.com/_index_template/zathras-timeseries-template" \
  -u "admin:password" -H 'Content-Type: application/json' \
  -d @opensearch_timeseries_template.json
```

### `export_config.example.yml`
Example configuration for OpenSearch and Horreum exporters.

**Setup:**
```bash
# Copy example to actual config
cp export_config.example.yml export_config.yml

# Edit with your credentials
vim export_config.yml
```

**Important:** `export_config.yml` is in `.gitignore` to prevent committing credentials.

## OpenSearch Connection

### Red Hat Internal OpenSearch
```yaml
opensearch:
  url: "https://opensearch.example.com/"
  index: "zathras-results"
  auth_token: "${OPENSEARCH_TOKEN}"
```

### Getting a Token
For Red Hat internal OpenSearch, obtain a token from:
- Internal SSO/Keycloak
- OpenSearch admin dashboard
- Or contact your OpenSearch administrator

### Testing Connection
```python
from post_processing.exporters.opensearch_exporter import OpenSearchExporter

exporter = OpenSearchExporter(
    url="https://opensearch.example.com/",
    index="zathras-results",
    auth_token="your-token"
)

# Test connection
if exporter.test_connection():
    print("✅ Connected to OpenSearch!")
else:
    print("❌ Connection failed")
```

## Index Template

The index template defines mappings for:

- **Metadata**: Document ID, type, version, timestamps
- **Test**: Name, version, description
- **System Under Test**: CPU, memory, NUMA, storage, network
- **Test Configuration**: Parameters, environment, tuning
- **Results**: Status, metrics, runs (object-based)
- **Runtime Info**: Start/stop times, command, user

### Dynamic Templates

1. **run_objects**: Maps `results.runs.run_*` to run objects
2. **timeseries_objects**: Maps `results.runs.*.timeseries.*` to time series points
3. **numa_nodes**: Maps `system_under_test.hardware.numa.node_*`
4. **storage_devices**: Maps `system_under_test.hardware.storage.device_*`
5. **network_interfaces**: Maps `system_under_test.hardware.network.interface_*`
6. **cpu_flags**: Maps CPU flags to boolean (e.g., `cpu.flags.avx2: true`)

## Querying Results

### Example Queries

**Find all CoreMark results:**
```json
GET /zathras-results/_search
{
  "query": {
    "term": { "test.name": "coremark" }
  }
}
```

**Find systems with AVX2 support:**
```json
GET /zathras-results/_search
{
  "query": {
    "term": { "system_under_test.hardware.cpu.flags.avx2": true }
  }
}
```

**Aggregate by CPU architecture:**
```json
GET /zathras-results/_search
{
  "size": 0,
  "aggs": {
    "by_architecture": {
      "terms": { "field": "system_under_test.hardware.cpu.architecture" }
    }
  }
}
```

**Get performance trends over time:**
```json
GET /zathras-results/_search
{
  "query": { "term": { "test.name": "coremark" }},
  "sort": [{ "metadata.collection_timestamp": "desc" }],
  "size": 100
}
```

**Query CoreMark validation data (nested):**
```json
GET /zathras-results/_search
{
  "query": {
    "nested": {
      "path": "results.runs.run_1.validation.threads",
      "query": {
        "bool": {
          "must": [
            {"term": {"results.runs.run_1.validation.threads.thread": 0}},
            {"term": {"results.runs.run_1.validation.threads.crcfinal": "0x65c5"}}
          ]
        }
      }
    }
  }
}
```

**Count validation CRCs across threads (nested aggregation):**
```json
GET /zathras-results/_search
{
  "size": 0,
  "aggs": {
    "validation_nested": {
      "nested": {"path": "results.runs.run_1.validation.threads"},
      "aggs": {
        "crc_values": {
          "terms": {"field": "results.runs.run_1.validation.threads.crcfinal"}
        }
      }
    }
  }
}
```

## Security

⚠️ **Important:**
- Never commit `export_config.yml` with real credentials
- Use environment variables for sensitive data
- Rotate tokens regularly
- Use SSL/TLS in production (`verify_ssl: true`)

## Field Limit Issue

### Problem
OpenSearch has a default field limit of **1,000** per index. High-core systems (64+ cores) can exceed this limit:

- CoreMark on 128-core system: ~1,000 fields (one per core + metadata)
- PyPerf on 96-core system: ~900 fields (90 benchmarks × cores)

**Error message:**
```
Limit of total fields [1000] has been exceeded
```

### Solution

**1. Nested Array Optimization (CoreMark)**

CoreMark validation data is stored as a **nested array** to reduce field count:

- **Before:** `validation.0_crcfinal`, `validation.1_crcfinal`, ... (1 field per thread)
- **After:** `validation.threads` (nested array, 1 field total)

**Field reduction on 256-core system:**
- Before: ~2,370 total fields (2,048 validation fields)
- After: ~334 total fields (18 validation fields)
- **Savings: 2,000+ fields (85% reduction)**

The index template defines `validation.threads` as `nested` type to preserve thread-to-CRC relationships.

**2. Multi-Document Processing (PyPerf)**

PyPerf creates one document per benchmark instead of bundling all benchmarks:
- Before: 1 document with 104 benchmarks × 256 cores = ~26,000 fields
- After: 104 documents with ~250 fields each

**3. Increased Field Limits**

The templates in this directory increase the limit to **5,000** for `zathras-results` and **2,000** for `zathras-timeseries`.

**If you have admin access:**
```bash
# Apply results template
curl -k -X PUT "https://opensearch.example.com/_index_template/zathras-results-template" \
  -u "admin:password" -H 'Content-Type: application/json' \
  -d @opensearch_index_template.json

# Apply timeseries template  
curl -k -X PUT "https://opensearch.example.com/_index_template/zathras-timeseries-template" \
  -u "admin:password" -H 'Content-Type: application/json' \
  -d @opensearch_timeseries_template.json
```

**If you need to request from your admin:**

Share this justification:

> **Request: Increase OpenSearch Field Limit**
> 
> **Current Issue:** The `zathras-results` index is hitting the default 1,000 field limit when indexing benchmark results from high-core systems (64+ cores).
> 
> **Requested Change:** Increase field limit to 5,000 for `zathras-results` and 2,000 for `zathras-timeseries`.
> 
> **Justification:**
> - Field count is bounded and predictable (based on CPU core count, max ~1,200 fields)
> - Two-index architecture already reduces fields per index
> - No dynamic user-generated field names (low risk)
> - 5,000 is well within OpenSearch's supported limits (10,000+)
> - Benchmarking high-core systems (128+ cores) is a core use case
> 
> **Alternatives considered:**
> - Aggregating per-core data (loses query granularity)
> - Splitting indices by core count (complicates queries)
> - Storing as JSON blobs (defeats purpose of structured search)
> 
> **Template files:** Available at `post_processing/config/opensearch_*_template.json`

### Downsides of Increasing Field Limit

1. **Memory Usage**: Each field mapping consumes memory per shard (~moderate increase)
2. **Query Performance**: Slight slowdown for wildcard searches (negligible for targeted queries)
3. **Indexing Performance**: Minor overhead maintaining more field mappings

**These downsides are acceptable** because:
- Field count is bounded (not unbounded user data)
- Read-heavy workload (analysis queries, not real-time indexing)
- Two-index architecture already mitigates concerns

## Troubleshooting

### Connection Errors
```
Error: Connection failed after 3 attempts
```
**Solution:** Check URL, verify network access, confirm token is valid

### SSL Certificate Errors
```
Error: SSL certificate verify failed
```
**Solution:** 
- For production: Get proper SSL certificate
- For testing only: Set `verify_ssl: false` (not recommended)

### Authentication Errors
```
Error: 401 Unauthorized
```
**Solution:** Check token is valid and has proper permissions

### Index Creation Errors
```
Error: 400 index_already_exists_exception
```
**Solution:** This is normal if index exists. Exporter handles this automatically.

### Field Limit Errors
```
Error: Limit of total fields [1000] has been exceeded
```
**Solution:** See the "Field Limit Issue" section above. You need to apply the index templates with increased field limits (requires admin permissions).

