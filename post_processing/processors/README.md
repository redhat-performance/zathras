# Zathras Benchmark Processors

This directory contains the processors that parse Zathras benchmark results and convert them into structured `ZathrasDocument` objects for export to OpenSearch and Horreum.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Base Processor](#base-processor)
- [Benchmark-Specific Processors](#benchmark-specific-processors)
- [Data Organization](#data-organization)
- [Creating a New Processor](#creating-a-new-processor)
- [Common Patterns](#common-patterns)

---

## Architecture Overview

The processor architecture follows a **template method pattern** with a base class that handles common functionality and benchmark-specific subclasses that implement parsing logic.

```
BaseProcessor (abstract)
├── CoreMarkProcessor
├── StreamsProcessor
├── SpecJBBProcessor
├── PyPerfProcessor (multi-document)
├── CoreMarkProProcessor
├── PassmarkProcessor
├── PhoronixProcessor
├── UperfProcessor
├── PigProcessor
├── AutoHPLProcessor
└── SpecCPU2017Processor
```

### Data Flow

```
Result ZIP File
    ↓
Archive Handler (extract)
    ↓
Benchmark Processor (parse)
    ↓
ZathrasDocument (structured)
    ↓
Exporters (OpenSearch/Horreum)
```

---

## Base Processor

**File:** `base_processor.py`

The `BaseProcessor` class provides a framework for parsing benchmark results and extracting common metadata.

### Core Responsibilities

1. **Archive Extraction**: Automatically extracts ZIP/TAR archives
2. **Metadata Extraction**: Parses directory paths for OS, cloud provider, instance type, iteration
3. **System Configuration**: Extracts CPU, memory, OS details from `sysconfig_info.tar`
4. **Test Configuration**: Parses test parameters from scenario files
5. **Document Assembly**: Builds complete `ZathrasDocument` objects
6. **Content Hashing**: Generates deterministic document IDs for deduplication

### Key Methods (Template Methods)

Subclasses **must** implement:

- `get_test_name()` → Returns the test name (e.g., "coremark", "specjbb")
- `parse_runs()` → Parses benchmark-specific results into `Run` objects

Subclasses **may** override:

- `build_results()` → Customizes the `Results` object (e.g., set primary metric)
- `build_test_configuration()` → Extracts test-specific configuration
- `build_test_info()` → Customizes test metadata

### Document Structure

The base processor builds a complete `ZathrasDocument`:

```python
ZathrasDocument
├── metadata                    # Base processor
│   ├── document_id            # Content hash
│   ├── test_timestamp         # From directory/ZIP
│   ├── processing_timestamp   # Current time
│   ├── os_vendor              # From path
│   ├── cloud_provider         # From path
│   ├── instance_type          # From path
│   ├── iteration              # From path
│   └── scenario_name          # From path
├── test                       # Base processor + subclass
│   ├── name                   # Subclass: get_test_name()
│   ├── version                # Extracted from result files
│   └── wrapper_version        # Extracted from result files
├── system_under_test          # Base processor
│   ├── hardware
│   │   ├── cpu
│   │   ├── memory
│   │   └── network
│   └── operating_system
├── test_configuration         # Base processor + subclass
│   ├── command_line
│   └── parameters
├── results                    # Subclass: parse_runs()
│   ├── status
│   ├── total_runs
│   ├── primary_metric
│   └── runs
│       ├── run_0
│       │   ├── run_number
│       │   ├── status
│       │   ├── metrics
│       │   ├── configuration
│       │   ├── timeseries
│       │   └── timeseries_summary
│       └── run_1
└── runtime_info               # Base processor
    └── execution_time
```

---

## Benchmark-Specific Processors

Each benchmark has a dedicated processor that inherits from `BaseProcessor` and implements benchmark-specific parsing logic.

### 1. CoreMark (`coremark_processor.py`)

**Benchmarks:** Multi-threaded integer performance

**Key Features:**
- Parses multiple runs (1 thread, all threads)
- Extracts validation CRC checksums as nested array to reduce field count
- Stores iterations per second as primary metric

**Data Structure:**
```python
Run:
  metrics:
    iterations: 123456789
    iterations_per_second: 987654.32
  validation:
    status: "PASS"
    seedcrc: "0xe9f5"
    threads: [
      {thread: 0, crcfinal: "0x1234", crclist: "0x5678", ...},
      {thread: 1, crcfinal: "0xabcd", ...}
    ]
```

**Field Count:** ~370 fields (reduced from 2,370 via nested array optimization)

---

### 2. STREAMS (`streams_processor.py`)

**Benchmarks:** Memory bandwidth (Copy, Scale, Add, Triad)

**Key Features:**
- Parses 4 STREAM operations
- Calculates aggregate bandwidth metrics
- Stores per-operation bandwidth rates

**Data Structure:**
```python
Run:
  metrics:
    avg_bandwidth_mb_per_s: 450000.0
    operations:
      Copy: {bandwidth_mb_per_s: 420000.0, ...}
      Scale: {bandwidth_mb_per_s: 430000.0, ...}
      Add: {bandwidth_mb_per_s: 460000.0, ...}
      Triad: {bandwidth_mb_per_s: 470000.0, ...}
```

---

### 3. SpecJBB (`specjbb_processor.py`)

**Benchmarks:** Java server performance

**Key Features:**
- Parses multiple transaction rate configurations
- Extracts critical-jOPS and max-jOPS
- Stores per-config throughput metrics

**Data Structure:**
```python
Run:
  metrics:
    critical_jops: 123456
    max_jops: 234567
    transaction_rates:
      "0064": {response_time_ms: 2.5, jops: 12345}
      "0128": {response_time_ms: 3.2, jops: 23456}
```

---

### 4. PyPerf (`pyperf_processor.py`)

**Benchmarks:** Python performance suite (104 benchmarks)

**Key Features:**
- **Multi-document mode**: Creates one document per benchmark to avoid field limits
- Overrides `process_multiple()` instead of `process()`
- Each document contains a single benchmark as `run_0`

**Data Structure:**
```python
# 104 separate documents
Document (pyperf_2to3):
  results:
    runs:
      run_0:
        metrics:
          benchmark_name: "2to3"
          mean_seconds: 1.234
          stddev_seconds: 0.012
```

**Why Multi-Document?**
- 104 benchmarks × ~250 fields = ~26,000 fields (exceeds 1,000 limit by 26x)
- Split into 104 documents × ~250 fields = under limit ✅

---

### 5. CoreMark Pro (`coremark_pro_processor.py`)

**Benchmarks:** Advanced workload performance

**Key Features:**
- Parses 9 workloads (cjpeg-rose7, core, linear_alg, loops, nnet, parser, radix2, sha, zip)
- Extracts marks per second for each workload
- Calculates composite score

**Data Structure:**
```python
Run:
  metrics:
    composite_score: 1234.56
    workloads:
      cjpeg-rose7: {marks_per_second: 123.45}
      core: {marks_per_second: 234.56}
      ...
```

---

### 6. Passmark (`passmark_processor.py`)

**Benchmarks:** CPU performance

**Key Features:**
- Parses 5 iterations
- Extracts CPU mark, single-thread rating, multi-thread rating
- Stores per-iteration scores

**Data Structure:**
```python
Run:
  metrics:
    cpu_mark_mean: 12345.67
    single_thread_rating_mean: 2345.67
    multi_thread_rating_mean: 23456.78
  timeseries:
    sequence_0: {timestamp: ..., metrics: {cpu_mark: 12345, iteration: 0}}
    sequence_1: {timestamp: ..., metrics: {cpu_mark: 12346, iteration: 1}}
```

---

### 7. Phoronix (`phoronix_processor.py`)

**Benchmarks:** Phoronix Test Suite

**Key Features:**
- Parses multiple test scenarios
- Extracts billion operations per second (BOPS)
- Stores per-test results

**Data Structure:**
```python
Run:
  metrics:
    avg_bops: 123.45
    tests:
      test1: {bops: 120.0, ...}
      test2: {bops: 125.0, ...}
```

---

### 8. Uperf (`uperf_processor.py`)

**Benchmarks:** Network performance

**Key Features:**
- Parses multiple protocol/packet size configurations
- Extracts throughput (Mbps), latency, transactions per second
- Stores time series for throughput over time

**Data Structure:**
```python
Run:
  metrics:
    avg_throughput_mbps: 9500.0
    configurations:
      tcp_8192: {throughput_mbps: 9800, latency_us: 45.2}
      udp_1024: {throughput_mbps: 8500, latency_us: 32.1}
  configuration:
    test_types: ["stream", "rr"]
    protocols: ["tcp", "udp"]
    packet_sizes: [64, 1024, 8192]
```

---

### 9. Pig (`pig_processor.py`)

**Benchmarks:** Apache Pig scheduling efficiency

**Key Features:**
- Parses scheduling efficiency at different thread counts
- Stores time series for each thread configuration
- Calculates mean, min, max, median, stddev

**Data Structure:**
```python
Run:
  metrics:
    average_sched_eff: 0.95
    min_sched_eff: 0.89
    max_sched_eff: 0.98
    thread_counts: [1, 2, 4, 8, 16, 32, 64, 128, 256]
  timeseries:
    sequence_0: {timestamp: ..., metrics: {threads: 1, sched_eff: 0.89}}
    sequence_1: {timestamp: ..., metrics: {threads: 2, sched_eff: 0.92}}
```

---

### 10. Auto HPL (`autohpl_processor.py`)

**Benchmarks:** High-Performance Linpack

**Key Features:**
- Parses GFLOPS, execution time, matrix size
- Extracts process grid configuration
- Single run with overall performance

**Data Structure:**
```python
Run:
  metrics:
    gflops: 8308.60
    time_seconds: 1639.91
    matrix_size: 273408
    block_size: 384
    process_grid_p: 4
    process_grid_q: 8
    total_processes: 32
  configuration:
    variant: "WR12R2R4"
    process_grid: "4x8"
```

---

### 11. SPEC CPU 2017 (`speccpu2017_processor.py`)

**Benchmarks:** SPEC CPU 2017 (Integer + Floating Point)

**Key Features:**
- **Two-run structure**: One run for integer suite, one for floating point suite
- Parses 25 total benchmarks (11 int + 14 fp)
- Calculates suite scores as geometric mean of rates
- Overall SPEC score as geometric mean of suite scores

**Data Structure:**
```python
Results:
  primary_metric:
    name: "spec_score"
    value: 958.11  # Geometric mean of both suites
  runs:
    run_0:  # Integer suite (intrate)
      metrics:
        suite_name: "intrate"
        base_score: 1032.43
        num_benchmarks: 11
        benchmarks:
          500.perlbench_r: {base_runtime: 391.57, base_rate: 1040.80}
          502.gcc_r: {base_runtime: 384.68, base_rate: 942.34}
          ...
    run_1:  # Floating point suite (fprate)
      metrics:
        suite_name: "fprate"
        base_score: 889.15
        num_benchmarks: 14
        benchmarks:
          503.bwaves_r: {base_runtime: 1652.95, base_rate: 1553.08}
          507.cactuBSSN_r: {base_runtime: 357.17, base_rate: 907.41}
          ...
```

**Field Count:** ~300 fields (well under 5,000 limit)

**Why Single Document?**
- 25 benchmarks with 2 suites = ~300 fields (no field limit issue)
- Preserves suite-level context (integer vs floating point)
- Overall SPEC score is meaningful composite metric
- Single test execution = single document (semantically correct)

---

## Data Organization

### Run Structure

Every benchmark result is organized into **runs**. A run represents a complete execution of the benchmark with specific configuration.

```python
Run:
  run_number: 0                    # Sequential run number
  status: "PASS" | "FAIL" | "UNKNOWN"
  metrics: {}                      # Benchmark-specific metrics
  configuration: {}                # Run-specific configuration
  timeseries: {}                   # Optional: time series data
  timeseries_summary: {}           # Optional: summary statistics
  start_time: "..."                # Optional: start timestamp
  end_time: "..."                  # Optional: end timestamp
  duration_seconds: 123.45         # Optional: duration
  validation: {}                   # Optional: validation data
```

### Time Series Structure

For benchmarks with time series data (e.g., Uperf throughput over time):

```python
timeseries:
  sequence_0:
    timestamp: "2025-11-17T12:00:00Z"
    metrics:
      throughput_mbps: 9500.0
      latency_us: 45.2
      sequence: 0
  sequence_1:
    timestamp: "2025-11-17T12:00:01Z"
    metrics:
      throughput_mbps: 9550.0
      latency_us: 44.8
      sequence: 1

timeseries_summary:
  count: 100
  mean: 9525.5
  median: 9520.0
  min: 9400.0
  max: 9650.0
  stddev: 50.2
  first_value: 9500.0
  last_value: 9530.0
```

### Metrics Organization

Metrics are organized hierarchically:

1. **Suite-level metrics** (SPEC CPU 2017): Overall suite performance
2. **Run-level metrics**: Overall benchmark performance
3. **Sub-metrics**: Per-operation, per-workload, per-benchmark breakdowns
4. **Time series**: Temporal data points

---

## Creating a New Processor

### Step 1: Create Processor File

Create a new file in `post_processing/processors/`:

```python
# post_processing/processors/mybenchmark_processor.py

from typing import Dict, Any
from pathlib import Path
import logging

from .base_processor import BaseProcessor
from ..schema import Run, create_run_key
from ..utils.parser_utils import parse_version_file, read_file_content

logger = logging.getLogger(__name__)


class MyBenchmarkProcessor(BaseProcessor):
    """
    Processor for MyBenchmark results.
    
    MyBenchmark measures XYZ performance across N configurations.
    """
    
    def get_test_name(self) -> str:
        """Return the test name as it appears in results_*.zip filename."""
        return "mybenchmark"
    
    def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse MyBenchmark runs into object-based structure.
        
        Args:
            extracted_result: {
                'files': [...],  # List of extracted files
                'extracted_path': Path(...)  # Path to extracted directory
            }
        
        Returns:
            {
                "run_0": {
                    "run_number": 0,
                    "status": "PASS",
                    "metrics": {...},
                    "configuration": {...}
                }
            }
        """
        result_dir = Path(extracted_result['extracted_path'])
        
        # 1. Find result files
        result_csv = result_dir / "results_mybenchmark.csv"
        if not result_csv.exists():
            logger.warning(f"Results file not found: {result_csv}")
            return {}
        
        # 2. Parse results
        data = self._parse_results(result_csv)
        
        # 3. Parse version
        version_file = result_dir / "version"
        version = parse_version_file(version_file) if version_file.exists() else None
        
        # 4. Determine status
        status_file = result_dir / "test_results_report"
        status = "PASS" if status_file.exists() else "UNKNOWN"
        
        # 5. Build run object
        run = Run(
            run_number=0,
            status=status,
            metrics={
                'score': data['score'],
                'throughput': data['throughput']
            },
            configuration={
                'version': version,
                'mode': data['mode']
            }
        )
        
        return {create_run_key(0): run}
    
    def _parse_results(self, csv_file: Path) -> Dict[str, Any]:
        """Parse the CSV file and extract metrics."""
        content = read_file_content(csv_file)
        # Parse CSV...
        return {'score': 1234.56, 'throughput': 9876.54, 'mode': 'standard'}
```

### Step 2: Register Processor

Add to `PROCESSOR_REGISTRY` in `run_postprocessing.py`:

```python
from .processors.mybenchmark_processor import MyBenchmarkProcessor

PROCESSOR_REGISTRY = {
    'coremark': CoreMarkProcessor,
    'streams': StreamsProcessor,
    # ... other processors ...
    'mybenchmark': MyBenchmarkProcessor,  # Add your processor
}
```

### Step 3: Test

```bash
# Test JSON generation
python3 -m post_processing.run_postprocessing \
    --input /path/to/results \
    --output-json /tmp/test_json/

# Test OpenSearch export
python3 -m post_processing.run_postprocessing \
    --input /path/to/results \
    --config export_config.yml \
    --opensearch
```

---

## Common Patterns

### Pattern 1: Multiple Runs

If your benchmark runs multiple iterations:

```python
def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Any]:
    runs = {}
    
    for i in range(num_iterations):
        data = self._parse_iteration(i)
        run = Run(
            run_number=i,
            status=data['status'],
            metrics=data['metrics'],
            configuration={'iteration': i}
        )
        runs[create_run_key(i)] = run
    
    return runs
```

### Pattern 2: Time Series Data

If your benchmark produces time series:

```python
from ..schema import TimeSeriesPoint, TimeSeriesSummary, create_sequence_key

timeseries = {}
values = []

for i, datapoint in enumerate(data_points):
    seq_key = create_sequence_key(i)
    timeseries[seq_key] = TimeSeriesPoint(
        timestamp=datapoint['timestamp'],
        metrics={
            'value': datapoint['value'],
            'sequence': i
        }
    )
    values.append(datapoint['value'])

# Calculate summary statistics
ts_summary = TimeSeriesSummary(
    count=len(values),
    mean=statistics.mean(values),
    median=statistics.median(values),
    min=min(values),
    max=max(values),
    stddev=statistics.stdev(values) if len(values) > 1 else None
)

run = Run(
    run_number=0,
    status="PASS",
    metrics={'avg_value': statistics.mean(values)},
    timeseries=timeseries,
    timeseries_summary=ts_summary
)
```

### Pattern 3: Multi-Document Processing

If your benchmark has too many fields (like PyPerf):

```python
def process_multiple(self) -> List[ZathrasDocument]:
    """Create multiple documents instead of one."""
    documents = []
    
    # Build common sections once
    base_metadata = self.build_metadata()
    test_info = self.build_test_info()
    sut = self.build_system_under_test()
    
    # Create one document per sub-benchmark
    for benchmark_name in benchmark_names:
        # Create document-specific metadata
        metadata = replace(base_metadata)
        metadata.scenario_name = f"{base_metadata.scenario_name}_{benchmark_name}"
        
        # Create results with single run
        results = Results(
            status="PASS",
            runs={"run_0": Run(...)}
        )
        
        # Create document
        document = ZathrasDocument(
            metadata=metadata,
            test=test_info,
            system_under_test=sut,
            results=results
        )
        
        # Calculate content hash
        content_hash = document.calculate_content_hash()
        document.metadata.document_id = f"{test_name}_{benchmark_name}_{content_hash[:16]}"
        
        documents.append(document)
    
    return documents
```

### Pattern 4: Nested Archive Extraction

If your results have nested archives (ZIP → TAR):

```python
# The archive handler automatically handles nested extraction
# Just access the final extracted path:

result_dir = Path(extracted_result['extracted_path'])

# For nested subdirectories:
result_subdir = result_dir / "result"
if not result_subdir.exists():
    result_subdir = result_dir  # Fallback

# Find files in subdirectory
csv_files = list(result_subdir.glob("*.csv"))
```

### Pattern 5: Suite-Based Organization

If your benchmark has multiple suites (like SPEC CPU 2017):

```python
runs = {}
run_num = 0

# Parse integer suite
int_data = self._parse_suite_csv(int_csv, "integer")
if int_data:
    runs[create_run_key(run_num)] = self._build_run_object(
        run_number=run_num,
        suite_data=int_data,
        suite_name="integer"
    )
    run_num += 1

# Parse floating point suite
fp_data = self._parse_suite_csv(fp_csv, "floating_point")
if fp_data:
    runs[create_run_key(run_num)] = self._build_run_object(
        run_number=run_num,
        suite_data=fp_data,
        suite_name="floating_point"
    )
    run_num += 1

return runs
```

---

## Best Practices

1. **Use helper methods**: Break parsing logic into small, testable functions
2. **Handle missing data gracefully**: Check for file existence, catch parsing errors
3. **Log appropriately**: Use `logger.info()` for success, `logger.warning()` for missing data, `logger.error()` for failures
4. **Calculate summary statistics**: For time series, always provide min/max/mean/median/stddev
5. **Sort lists for determinism**: Use `sorted()` for any lists to ensure consistent content hashing
6. **Document your processor**: Add docstrings explaining the data format and structure
7. **Test with real data**: Always test with actual benchmark output files
8. **Consider field limits**: If > 1,000 fields, consider multi-document approach

---

## Field Limit Considerations

OpenSearch has a default field limit of **1,000 fields per index** (increased to 5,000 with custom templates).

### When to Split into Multiple Documents

**Split if:**
- Total fields would exceed 1,000 (or 5,000 with templates)
- Example: PyPerf with 104 benchmarks × 250 fields = 26,000 fields

**Keep as single document if:**
- Total fields < 1,000 comfortably
- Natural groupings exist (like SPEC CPU 2017 suites)
- Combined/overall score is meaningful
- Represents a single test execution

---

## Utility Functions

Import from `parser_utils.py`:

```python
from ..utils.parser_utils import (
    parse_version_file,      # Parse version from text file
    read_file_content,       # Read file with encoding handling
    safe_float,              # Parse float with fallback
    safe_int,                # Parse int with fallback
)

from ..schema import (
    create_run_key,          # Create "run_0", "run_1", ...
    create_sequence_key,     # Create "sequence_0", "sequence_1", ...
)
```

---

## Debugging Tips

1. **Output JSON**: Use `--output-json` to inspect generated documents
   ```bash
   python3 -m post_processing.run_postprocessing \
       --input /path/to/results \
       --output-json /tmp/debug_json/
   ```

2. **Check extraction**: Look at `extracted_result['extracted_path']` contents
   ```python
   logger.info(f"Extracted files: {list(result_dir.glob('*'))}")
   ```

3. **Verify field count**: Count unique field paths in generated JSON
   ```python
   python3 -c "
   import json
   from pathlib import Path
   
   def count_fields(obj, prefix=''):
       count = 0
       if isinstance(obj, dict):
           for k, v in obj.items():
               count += count_fields(v, f'{prefix}.{k}' if prefix else k)
       elif isinstance(obj, list) and obj:
           count += count_fields(obj[0], f'{prefix}[]')
       else:
           count += 1
       return count
   
   data = json.load(open('/tmp/debug_json/mybenchmark_abc123.json'))
   print(f'Total fields: {count_fields(data)}')
   "
   ```

4. **Test deduplication**: Run processing twice and verify duplicates are skipped
   ```bash
   # First run
   python3 -m post_processing.run_postprocessing ... --opensearch
   
   # Second run (should show all duplicates)
   python3 -m post_processing.run_postprocessing ... --opensearch
   ```

---

## Additional Resources

- **Schema Documentation**: See `post_processing/schema.py` for data structure definitions
- **Base Processor Source**: See `base_processor.py` for full implementation
- **Example Processors**: Review existing processors for patterns
- **Testing Guide**: See `post_processing/README.md` for testing instructions

---

## Questions?

For questions or issues, refer to:
- Main README: `post_processing/README.md`
- Schema documentation: `post_processing/schema.py`
- Implementation TODO: `post_processing/IMPLEMENTATION_TODO.md`

