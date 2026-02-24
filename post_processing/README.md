# Zathras Post-Processing

Export Zathras benchmark results to OpenSearch or Horreum for centralized analysis, dashboards, and performance tracking.

---

## How to Run

Process entire result directories automatically:

```bash
# 1. Configure credentials
cp post_processing/config/export_config_example.yml post_processing/config/export_config.yml
vim post_processing/config/export_config.yml  # Add your credentials

# 2. Process and export everything
python3 -m post_processing.run_postprocessing \
    --input /path/to/results \
    --config post_processing/config/export_config.yml \
    --opensearch

# Or just generate JSON files
python3 -m post_processing.run_postprocessing \
    --input /path/to/results \
    --output-json /tmp/json_output
```

**What it does:**
- Recursively discovers all result directories
- Auto-detects benchmark types (coremark, streams, pyperf, etc.)
- Batch processes all results
- Exports to OpenSearch/Horreum or saves JSON
- Provides detailed summary report

**Example output:**
```
2025-11-06 21:00:31 - Searching for results in: production_data
2025-11-06 21:00:31 - Found 34 result directory(ies)
2025-11-06 21:00:34 - Processing coremark: results_coremark.zip
  [SUCCESS] Parsed coremark: coremark_Standard_D128ds_v6_2_20251107_020034
  [EXPORT] Exported to OpenSearch (summary): coremark_Standard_D128ds_v6_2_20251107_020034

======================================================================
PROCESSING SUMMARY
======================================================================
Total: 109 files
Successful: 78 benchmarks
Skipped: 31 (unknown types)
Duration: 109.38 seconds

Tests Processed:
  - coremark: 12
  - streams: 11
  - pyperf: 6 (34,080 time series points)
  - specjbb: 11
  - And more...
```

---

## Detailed Usage

### Benchmark Support Status

| Benchmark | Post-Processing Support | Processor | Notes |
|-----------|------------------------|-----------|-------|
| CoreMark | Supported | `coremark_processor.py` | Single-thread CPU performance |
| CoreMark Pro | Supported | `coremark_pro_processor.py` | 9 workload types |
| FIO | Supported | `fio_processor.py` | Flexible I/O tester |
| HPL (autohpl) | Supported | `autohpl_processor.py` | High Performance Computing Linpack |
| Passmark | Supported | `passmark_processor.py` | CPU & Memory marks |
| Phoronix Test Suite | Supported | `phoronix_processor.py` | 51 sub-tests (BOPs) |
| Pig | Supported | `pig_processor.py` | Processor scheduler efficiency |
| PyPerf | Supported | `pyperf_processor.py` | 90 Python benchmarks, 5,680 time series points |
| SPEC CPU 2017 | Supported | `speccpu2017_processor.py` | Compute-intensive performance suite |
| SpecJBB | Supported | `specjbb_processor.py` | Java business benchmark (Critical/Max-jOPS) |
| STREAM | Supported | `streams_processor.py` | Memory bandwidth (Copy, Scale, Add, Triad) |
| Uperf | Supported | `uperf_processor.py` | Network performance (IOPS, latency, throughput) |
| HammerDB | Not Supported | - | Database benchmarking (MariaDB, PostgreSQL) |
| IOzone | Not Supported | - | File system benchmarking |
| Linpack | Not Supported | - | Licensed Linpack benchmark |
| NUMA STREAM | Not Supported | - | NUMA memory bandwidth extension |

**12 of 16 benchmarks supported** | **35,000+ time series points per production run**

---

## Installation & Setup

### Prerequisites
- Python 3.8+
- Zathras benchmark results
- OpenSearch or Horreum access (optional for local testing)

### Install Dependencies

```bash
cd /path/to/zathras
pip3 install -r post_processing/requirements.txt
```

**Dependencies:**
- `pyyaml` - Configuration and result parsing
- `python-dateutil` - Timestamp handling
- `requests` - HTTP for Horreum

### Configuration

Create your configuration file:

```bash
# Copy example
cp post_processing/config/export_config_example.yml post_processing/config/export_config.yml

# Edit with your settings
vim post_processing/config/export_config.yml
```

Example config:
```yaml
opensearch:
  url: "https://opensearch.example.com"
  summary_index: "zathras-results"        # Summary documents
  timeseries_index: "zathras-timeseries"  # Individual time series points
  username: "example-user"
  password: "your-password"
  verify_ssl: false  # Set to true for production

horreum:
  url: "http://localhost:8080"
  username: "your-horreum-username"
  password: "your-horreum-password"
  test_name: "Zathras Benchmarks"

processing:
  batch_size: 500
  continue_on_error: true
  verbose: false
```

---

## CI/CD Integration with Burden

### Automatic Export After Every Benchmark Run

Modify the `burden` script to automatically export results after test completion:

```bash
# Add to burden script after test execution completes
# Around line where results are finalized (e.g., after archiving)

if [ -f "post_processing/config/export_config.yml" ]; then
    echo "Exporting results to OpenSearch..."
    python3 -m post_processing.run_postprocessing \
        --input "${RESULT_DIR}" \
        --config post_processing/config/export_config.yml \
        --opensearch || {
        echo "WARNING: Post-processing export failed, but continuing..."
    }
else
    echo "INFO: No export config found, skipping post-processing export"
fi
```

**Benefits:**
- Zero manual intervention
- Results exported immediately after completion
- Fails gracefully if config missing
- Works with all burden scenarios
- Automatic for all team members

**Location in burden script:**
- Add after result archiving (near `tar` operations)
- Before final status reporting
- Ensure `RESULT_DIR` variable points to the top-level result directory

**One-time setup:**
```bash
# Create config file (once per system/CI environment)
cp post_processing/config/export_config_example.yml post_processing/config/export_config.yml
vim post_processing/config/export_config.yml  # Add your credentials
```

---

## View Your Results

### OpenSearch Dashboards

Access your exported data:
- **Discover:** https://your-opensearch-url/_dashboards/app/discover
- **Dev Tools:** https://your-opensearch-url/_dashboards/app/dev_tools

### Quick Queries

```json
# Get latest results
GET /zathras-results/_search
{
  "size": 10,
  "sort": [{ "metadata.test_timestamp": "desc" }]
}

# Find CoreMark results
GET /zathras-results/_search
{
  "query": { "term": { "test.name": "coremark" }}
}

# Performance over time (summary data)
GET /zathras-results/_search
{
  "query": { "term": { "test.name": "coremark" }},
  "sort": [{ "metadata.test_timestamp": "asc" }],
  "_source": ["metadata.test_timestamp", "results.runs.run_0.mean"]
}

# Get time series data points
GET /zathras-timeseries/_search
{
  "query": { 
    "bool": {
      "must": [
        { "term": { "test.name": "pyperf" }},
        { "term": { "results.run.benchmark_name": "2to3" }}
      ]
    }
  },
  "sort": [{ "metadata.sequence": "asc" }]
}

# Compare by CPU architecture
GET /zathras-results/_search
{
  "size": 0,
  "aggs": {
    "by_arch": {
      "terms": { "field": "system_under_test.hardware.cpu.architecture.keyword" },
      "aggs": {
        "avg_performance": { "avg": { "field": "results.runs.run_0.mean" }}
      }
    }
  }
}
```

---

## What Gets Extracted

The post-processing pipeline automatically extracts and structures data from Zathras result files:

### Benchmark Results (`results_*.zip`)
- **Performance metrics**: Mean, median, min, max, standard deviation for each run
- **Time series data**: Individual data points with sequence ordering (for benchmarks like PyPerf)
- **Configuration details**: Test-specific settings and parameters
- **Execution metadata**: Start time, duration, status (PASS/FAIL)
- **Validation data**: Checksums, compiler information

### System Configuration (`sysconfig_info.tar`)
**Hardware:**
- **CPU**: Vendor, model, architecture, cores, threads, cache sizes, CPU flags (as boolean objects)
- **Memory**: Total capacity, speed, NUMA topology (node-based objects)
- **Storage**: Devices, capacity, types, mount points
- **Network**: Interfaces, speeds, addresses

**Operating System:**
- Distribution, version, kernel version
- Tuned profile settings
- Sysctl parameters
- SELinux configuration

### Test Configuration (`ansible_vars.yml`)
- Test parameters and iteration counts
- System tuning settings applied during test
- Zathras scenario information

### Directory Metadata (from path structure)
Automatically parsed from result directory paths:
- **OS Vendor**: e.g., `rhel`, `ubuntu`, `fedora`
- **Cloud Provider**: e.g., `azure`, `aws`, `gcp`, `local`
- **Instance Type**: e.g., `Standard_D8ds_v6`, `m5.xlarge`
- **Iteration Number**: e.g., `0`, `1`, `2`
- **Scenario Name**: e.g., `az_rhel_10_ga`

Example directory structure: `production_data/az_rhel_10_ga/rhel/azure/Standard_D8ds_v6_1/`

---

## Export to Different Targets

### OpenSearch (Two-Index Architecture)

Zathras uses **two OpenSearch indices** to handle high-volume time series data:

1. **`zathras-results`** - Summary documents with aggregated statistics (mean, median, stdev, etc.)
2. **`zathras-timeseries`** - Individual time series data points (one document per point)

**Why two indices?** Benchmarks like PyPerf generate 5,680+ time series points per test, exceeding OpenSearch's 5,000 field limit for a single document. The two-index approach keeps summaries queryable while preserving full time series data.

```bash
# Automatically handles both indices
python3 -m post_processing.run_postprocessing \
    --input /path/to/results \
    --config post_processing/config/export_config.yml \
    --opensearch
```

### Horreum

```python
from post_processing.exporters.horreum_exporter import HorreumExporter

exporter = HorreumExporter(
    url="https://horreum.example.com",
    test_name="zathras-coremark",
    auth_token="your-token",
    owner="your-team",
    access="PUBLIC"
)

# Export run
run_id = exporter.export_zathras_document(document)
print(f"Run ID: {run_id}")
```

---

## Duplicate Prevention

Zathras uses **content-based checksums** to prevent duplicate documents when reprocessing the same test results.

### How It Works

Each document is assigned a deterministic ID based on a SHA256 hash of its content:

```
Document ID = {test_name}_{content_hash[:16]}
Example: coremark_fdcfbbf0e6a525ea
```

The hash includes:
- Test name, version, and configuration
- System details (CPU, memory, OS)
- All benchmark results and metrics
- Original test timestamp

The hash **excludes** `processing_timestamp`, ensuring identical test results always generate the same ID.

### Benefits

**Prevents Duplicates:**
```bash
# Process results
python3 -m post_processing.run_postprocessing --input results/ --opensearch

# Reprocess same results (e.g., after fixing a bug)
python3 -m post_processing.run_postprocessing --input results/ --opensearch

# Result: Same document updated in OpenSearch, no duplicate created
```

**Safe Reprocessing:**
- Fix processor bugs without creating duplicates
- Add new fields to existing documents
- Update metadata or extractors
- Track last processing time via `processing_timestamp`

**OpenSearch Behavior:**
```python
# First upload
POST /zathras-results/_doc/coremark_fdcfbbf0e6a525ea
→ Creates new document

# Second upload (same test results, different processing time)
POST /zathras-results/_doc/coremark_fdcfbbf0e6a525ea
→ Updates existing document (no duplicate)
```

### When Duplicates WILL Occur

Duplicates only happen when **actual test data differs**:

- Different test runs (different timestamps/results)
- Different systems (different CPU/memory)
- Different configurations (different parameters)

This is expected behavior representing genuinely different tests.

### Testing

Deduplication is built-in and automatic. To verify it's working, process the same results twice and query OpenSearch - you'll see only one document exists with an updated `processing_timestamp`.

---

## Schema & Data Structure

### Two-Index Architecture

Zathras uses two separate OpenSearch indices to efficiently handle benchmarks with large time series datasets:

**1. `zathras-results` - Summary Documents**

Contains aggregated statistics for each benchmark execution:

```json
{
  "metadata": {
    "document_id": "coremark_Standard_D8ds_v6_1_20251106",
    "test_timestamp": "2025-11-06T12:00:00Z",
    "processing_timestamp": "2025-11-06T12:05:00Z",
    "os_vendor": "rhel",
    "cloud_provider": "azure",
    "instance_type": "Standard_D8ds_v6",
    "iteration": 1,
    "scenario_name": "az_rhel_10_ga"
  },
  "test": {
    "name": "coremark",
    "version": "1.0"
  },
  "system_under_test": {
    "hardware": {
      "cpu": {
        "vendor": "Intel",
        "model": "Xeon Platinum 8370C",
        "architecture": "x86_64",
        "cores": 8,
        "threads": 16,
        "flags": { "avx2": true, "avx512": true, "sse4_2": true }
      },
      "memory": {
        "total_gb": 32,
        "speed_mhz": 3200
      }
    },
    "os": {
      "vendor": "rhel",
      "version": "10.0",
      "kernel": "6.11.0-0.rc5.20240828git6a0e38f.45.el10.x86_64"
    }
  },
  "results": {
    "runs": {
      "run_0": {
        "status": "PASS",
        "mean": 193245.2,
        "median": 193500.0,
        "stdev": 1234.5,
        "min": 191000.0,
        "max": 195000.0
      }
    }
  }
}
```

**2. `zathras-timeseries` - Individual Time Series Points**

Stores each time series data point as a separate, fully denormalized document:

```json
{
  "metadata": {
    "document_id": "pyperf_Standard_D8ds_v6_1_20251106",
    "timeseries_id": "pyperf_Standard_D8ds_v6_1_20251106_run0_2to3_seq0",
    "timestamp": "2025-11-06T12:00:00Z",
    "sequence": 0,
    "test_timestamp": "2025-11-06T12:00:00Z",
    "processing_timestamp": "2025-11-06T12:05:00Z",
    "os_vendor": "rhel",
    "cloud_provider": "azure",
    "instance_type": "Standard_D8ds_v6",
    "iteration": 1
  },
  "test": {
    "name": "pyperf",
    "version": "1.0"
  },
  "system_under_test": {
    /* Full SUT details included */
  },
  "results": {
    "run": {
      "run_key": "run_0",
      "run_number": 0,
      "status": "PASS",
      "benchmark_name": "2to3"
    },
    "value": 1.23,
    "unit": "seconds"
  }
}
```

### Design Principles

**Fully Denormalized**
- Each document contains complete context (test, SUT, configuration)
- No joins required for querying
- Optimized for document-oriented datastores

**Object-Based Structure**
- Dynamic keys like `run_0`, `node_0`, `device_0` instead of arrays
- Better OpenSearch performance for aggregations
- Avoids nested object limitations

**Hierarchical Metadata**
- Structured extraction from directory paths
- Consistent field naming across indices
- Enables filtering by cloud provider, instance type, iteration

**Dual Timestamps**
- `test_timestamp`: When the benchmark was executed
- `processing_timestamp`: When the JSON document was created
- Enables tracking of both test execution and data pipeline timing

**Boolean CPU Flags**
- CPU features represented as objects: `{"avx2": true, "avx512": false}`
- Efficient term queries for hardware capability filtering

---

## Advanced Queries

### Performance Regression Detection

```json
GET /zathras-results/_search
{
  "query": {
    "bool": {
      "must": [
        { "term": { "test.name": "coremark" }},
        { "range": { "metadata.test_timestamp": { "gte": "now-7d" }}}
      ]
    }
  },
  "sort": [{ "metadata.test_timestamp": "asc" }],
  "_source": ["metadata.test_timestamp", "results.runs.run_0.mean", "metadata.instance_type"]
}
```

### Hardware Comparison

```json
GET /zathras-results/_search
{
  "query": { "term": { "test.name": "coremark" }},
  "aggs": {
    "by_cpu_model": {
      "terms": { "field": "system_under_test.hardware.cpu.model.keyword", "size": 10 },
      "aggs": {
        "avg_performance": { "avg": { "field": "results.runs.run_0.mean" }},
        "max_performance": { "max": { "field": "results.runs.run_0.max" }}
      }
    }
  }
}
```

### Find Systems with Specific Features

```json
# Systems with AVX-512 and more than 64 cores
GET /zathras-results/_search
{
  "query": {
    "bool": {
      "must": [
        { "term": { "system_under_test.hardware.cpu.flags.avx512": true }},
        { "range": { "system_under_test.hardware.cpu.cores": { "gt": 64 }}}
      ]
    }
  },
  "_source": ["system_under_test.hardware.cpu", "metadata.instance_type", "results.runs.run_0.mean"]
}
```

### Time Series Analysis

```json
# Get all time series points for a specific benchmark run
GET /zathras-timeseries/_search
{
  "query": {
    "bool": {
      "must": [
        { "term": { "metadata.document_id": "pyperf_Standard_D8ds_v6_1_20251107" }},
        { "term": { "results.run.benchmark_name": "2to3" }}
      ]
    }
  },
  "sort": [{ "metadata.sequence": "asc" }],
  "size": 100
}

# Aggregate time series data
GET /zathras-timeseries/_search
{
  "query": { "term": { "test.name": "pyperf" }},
  "aggs": {
    "by_benchmark": {
      "terms": { "field": "results.run.benchmark_name.keyword" },
      "aggs": {
        "avg_value": { "avg": { "field": "results.value" }},
        "min_value": { "min": { "field": "results.value" }},
        "max_value": { "max": { "field": "results.value" }}
      }
    }
  }
}
```

---

## Additional Resources

### Documentation
- [Schema Analysis](DATA_ANALYSIS.md) - Detailed schema documentation
- [Implementation Plan](IMPLEMENTATION_TODO.md) - Development roadmap
- [Index Template](config/opensearch_index_template.json) - OpenSearch mappings

### Zathras Documentation
- [Main README](../README.md)
- [Testing Quickstart](../docs/testing_quickstart.md)
- [Command Line Reference](../docs/command_line_reference.md)

### External Resources
- [OpenSearch Query DSL](https://opensearch.org/docs/latest/query-dsl/)
- [OpenSearch Aggregations](https://opensearch.org/docs/latest/aggregations/)
- [Horreum Documentation](https://horreum.hyperfoil.io/)

