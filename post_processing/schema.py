"""
Zathras Post-Processing Schema Definition

This module defines the object-based schema structure for Zathras benchmark results.
Uses dataclasses for type safety and validation.

Key Design Decisions:
- Object-based structure with dynamic keys (runs.run_1, runs.run_2)
- Timestamps as keys for time series data
- No nested arrays (avoids OpenSearch performance issues)
- Fully denormalized (all SUT metadata embedded)
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import hashlib
import copy


@dataclass
class Metadata:
    """Document metadata section"""
    document_id: str
    document_type: str = "zathras_test_result"
    zathras_version: str = "1.0"

    # Timestamps
    test_timestamp: Optional[str] = None  # When the test was actually executed
    # When JSON was created
    processing_timestamp: str = field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z"
    )

    # Deprecated (kept for backward compatibility, use test_timestamp instead)
    collection_timestamp: Optional[str] = None

    # Source directory breakdown (e.g., rhel/azure/Standard_D8ds_v6_1)
    os_vendor: Optional[str] = None
    cloud_provider: Optional[str] = None
    instance_type: Optional[str] = None
    iteration: Optional[int] = None
    scenario_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class TestInfo:
    """Test information section"""
    name: str
    version: str
    wrapper_version: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class CPUInfo:
    """CPU hardware information"""
    vendor: Optional[str] = None
    model: Optional[str] = None
    architecture: Optional[str] = None
    cores: Optional[int] = None
    threads_per_core: Optional[int] = None
    sockets: Optional[int] = None
    numa_nodes: Optional[int] = None
    frequency_mhz: Optional[float] = None
    cache_l1d: Optional[str] = None
    cache_l1i: Optional[str] = None
    cache_l2: Optional[str] = None
    cache_l3: Optional[str] = None
    flags: Dict[str, bool] = field(default_factory=dict)  # Boolean object: {avx2: true, sse4: true}

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class MemoryInfo:
    """Memory hardware information"""
    total_gb: Optional[int] = None
    total_kb: Optional[int] = None
    available_kb: Optional[int] = None
    speed_mhz: Optional[int] = None
    type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class HardwareInfo:
    """Complete hardware information with object-based structure"""
    cpu: Optional[CPUInfo] = None
    memory: Optional[MemoryInfo] = None
    numa: Optional[Dict[str, Any]] = None  # node_0, node_1, etc.
    storage: Optional[Dict[str, Any]] = None  # device_0, device_1, etc.
    network: Optional[Dict[str, Any]] = None  # interface_0, interface_1, etc.

    def to_dict(self) -> Dict[str, Any]:
        result = {}
        if self.cpu:
            result['cpu'] = self.cpu.to_dict()
        if self.memory:
            result['memory'] = self.memory.to_dict()
        if self.numa:
            result['numa'] = self.numa
        if self.storage:
            result['storage'] = self.storage
        if self.network:
            result['network'] = self.network
        return result


@dataclass
class OperatingSystemInfo:
    """Operating system information"""
    distribution: Optional[str] = None
    version: Optional[str] = None
    kernel_version: Optional[str] = None
    hostname: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class ConfigurationInfo:
    """System configuration information"""
    tuned_profile: Optional[str] = None
    selinux_status: Optional[str] = None
    transparent_hugepages: Optional[str] = None
    sysctl_parameters: Optional[Dict[str, str]] = None
    kernel_parameters: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class SystemUnderTest:
    """Complete System Under Test metadata"""
    hardware: Optional[HardwareInfo] = None
    operating_system: Optional[OperatingSystemInfo] = None
    configuration: Optional[ConfigurationInfo] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {}
        if self.hardware:
            result['hardware'] = self.hardware.to_dict()
        if self.operating_system:
            result['operating_system'] = self.operating_system.to_dict()
        if self.configuration:
            result['configuration'] = self.configuration.to_dict()
        return result


@dataclass
class TestConfiguration:
    """Test configuration parameters"""
    iterations_requested: Optional[int] = None
    parameters: Optional[Dict[str, Any]] = None
    environment: Optional[Dict[str, str]] = None
    tuning: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class PrimaryMetric:
    """Primary performance metric"""
    name: str
    value: float
    unit: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StatisticalSummary:
    """Statistical summary across all runs"""
    mean: Optional[float] = None
    median: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    stddev: Optional[float] = None
    variance: Optional[float] = None
    sample_count: Optional[int] = None
    percentile_95: Optional[float] = None
    percentile_99: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class TimeSeriesPoint:
    """
    Single time series data point

    Object-based structure with timestamp and metrics:
    {
      "timestamp": "2025-11-06T12:00:00.000Z",
      "metrics": {
        "iterations_per_second": 193245.2,
        "cpu_utilization": 98.5
      }
    }
    """
    timestamp: str  # ISO 8601 timestamp string
    metrics: Dict[str, float] = field(default_factory=dict)  # Named metrics with values

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TimeSeriesSummary:
    """Summary statistics for time series within a run"""
    count: Optional[int] = None
    mean: Optional[float] = None
    median: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    stddev: Optional[float] = None
    first_value: Optional[float] = None
    last_value: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Run:
    """Single benchmark run with object-based time series"""
    run_number: int
    status: str = "UNKNOWN"
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    configuration: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None
    timeseries_summary: Optional[TimeSeriesSummary] = None
    timeseries: Optional[Dict[str, TimeSeriesPoint]] = None  # Sequence keys: "sequence_0", "sequence_1", etc.
    validation: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "run_number": self.run_number,
            "status": self.status
        }

        if self.start_time:
            result['start_time'] = self.start_time
        if self.end_time:
            result['end_time'] = self.end_time
        if self.duration_seconds is not None:
            result['duration_seconds'] = self.duration_seconds
        if self.configuration:
            result['configuration'] = self.configuration
        if self.metrics:
            result['metrics'] = self.metrics
        if self.timeseries_summary:
            result['timeseries_summary'] = self.timeseries_summary.to_dict()
        if self.timeseries:
            # Convert TimeSeriesPoint objects to dicts
            result['timeseries'] = {
                timestamp: point.to_dict() if isinstance(point, TimeSeriesPoint) else point
                for timestamp, point in self.timeseries.items()
            }
        if self.validation:
            result['validation'] = self.validation

        return result


@dataclass
class Results:
    """Complete results section with object-based runs"""
    status: str = "UNKNOWN"
    execution_time_seconds: Optional[float] = None
    total_runs: Optional[int] = None
    primary_metric: Optional[PrimaryMetric] = None
    overall_statistics: Optional[StatisticalSummary] = None
    runs: Optional[Dict[str, Run]] = None  # run_1, run_2, etc. as keys

    def to_dict(self) -> Dict[str, Any]:
        result = {"status": self.status}

        if self.execution_time_seconds is not None:
            result['execution_time_seconds'] = self.execution_time_seconds
        if self.total_runs is not None:
            result['total_runs'] = self.total_runs
        if self.primary_metric:
            result['primary_metric'] = self.primary_metric.to_dict()
        if self.overall_statistics:
            result['overall_statistics'] = self.overall_statistics.to_dict()
        if self.runs:
            # Convert Run objects to dicts with run_1, run_2 keys
            result['runs'] = {
                run_key: run.to_dict() if isinstance(run, Run) else run
                for run_key, run in self.runs.items()
            }

        return result


@dataclass
class RuntimeInfo:
    """Runtime execution information"""
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    command: Optional[str] = None
    working_directory: Optional[str] = None
    user: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class ZathrasDocument:
    """Complete Zathras benchmark result document"""
    metadata: Metadata
    test: TestInfo
    system_under_test: SystemUnderTest
    test_configuration: TestConfiguration
    results: Results
    runtime_info: Optional[RuntimeInfo] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "metadata": self.metadata.to_dict(),
            "test": self.test.to_dict(),
            "system_under_test": self.system_under_test.to_dict(),
            "test_configuration": self.test_configuration.to_dict(),
            "results": self.results.to_dict()
        }

        if self.runtime_info:
            result['runtime_info'] = self.runtime_info.to_dict()

        return result

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=indent)

    def calculate_content_hash(self, exclude_processing_timestamp: bool = True) -> str:
        """
        Calculate a deterministic SHA256 hash of the document content.

        This hash is based on the actual test data and excludes timestamps
        that change during processing, making it suitable for duplicate detection.

        The hash is based on:
        - Test results summary metrics (not timeseries points)
        - System Under Test (hardware, OS, config)
        - Test configuration (parameters, workloads)

        The hash excludes:
        - All timestamps (test_timestamp, processing_timestamp, collection_timestamp)
        - Document ID (computed from hash)
        - Timeseries data (stored separately, often has synthetic timestamps)

        Args:
            exclude_processing_timestamp: If True, excludes all timestamp fields
                                         from the hash calculation

        Returns:
            Hex string of SHA256 hash (64 characters)
        """
        # Use summary-only data (excludes timeseries which often has synthetic timestamps)
        doc_dict = copy.deepcopy(self.to_dict_summary_only())

        # Remove fields that change on re-processing or are metadata-only
        if exclude_processing_timestamp and 'metadata' in doc_dict:
            # Remove ALL timestamps - they're metadata, not test results
            doc_dict['metadata'].pop('processing_timestamp', None)
            doc_dict['metadata'].pop('test_timestamp', None)
            doc_dict['metadata'].pop('collection_timestamp', None)
            # Also remove document_id as we're computing it
            doc_dict['metadata'].pop('document_id', None)

        # Sort keys for deterministic ordering
        sorted_json = json.dumps(doc_dict, sort_keys=True, separators=(',', ':'))

        # Calculate SHA256 hash
        hash_obj = hashlib.sha256(sorted_json.encode('utf-8'))
        return hash_obj.hexdigest()

    def to_dict_summary_only(self) -> Dict[str, Any]:
        """
        Convert to dictionary WITHOUT timeseries data.
        Only includes timeseries_summary for each run.
        Used for the main zathras-results index.
        """
        result = self.to_dict()

        # Remove timeseries from all runs
        if 'results' in result and 'runs' in result['results']:
            for run_key, run_data in result['results']['runs'].items():
                if 'timeseries' in run_data:
                    del run_data['timeseries']

        return result

    def extract_timeseries_documents(self) -> List['TimeSeriesDocument']:
        """
        Extract all time series points as individual TimeSeriesDocument objects.
        Used for the zathras-timeseries index.

        Maintains same top-level structure as summary document for consistency.

        Returns list of TimeSeriesDocument objects (one per time series point).
        """
        ts_docs = []

        # Iterate through all runs
        for run_key, run in self.results.runs.items():
            if not run.timeseries:
                continue

            # Get benchmark name (for multi-benchmark tests like PyPerf)
            benchmark_name = run.metrics.get('benchmark_name') if run.metrics else None
            benchmark_desc = run.metrics.get('description') if run.metrics else None

            # Determine unit from first metric or default
            unit = "unknown"
            if run.metrics:
                # Try to infer unit from metric names
                for metric_name in run.metrics.keys():
                    if 'seconds' in metric_name or '_sec' in metric_name:
                        unit = "seconds"
                        break
                    elif 'bops' in metric_name:
                        unit = "bops"
                        break
                    elif 'mb_per_sec' in metric_name or 'bandwidth' in metric_name:
                        unit = "MB/s"
                        break

            # Process each time series point
            for seq_key, ts_point in run.timeseries.items():
                # Extract sequence number from key (e.g., "sequence_0" -> 0)
                sequence = int(seq_key.split('_')[1])

                # Generate unique timeseries_id
                ts_id = f"{self.metadata.document_id}_{run_key}_{seq_key}"

                # Get primary value (first metric or explicit 'value' field)
                value = None
                point_metrics = {}

                if ts_point.metrics:
                    # Look for common value field names
                    if 'value_seconds' in ts_point.metrics:
                        value = ts_point.metrics['value_seconds']
                        point_metrics = {k: v for k, v in ts_point.metrics.items() if k != 'value_seconds'}
                    elif 'throughput_bops' in ts_point.metrics:
                        value = ts_point.metrics['throughput_bops']
                        point_metrics = {k: v for k, v in ts_point.metrics.items() if k != 'throughput_bops'}
                    elif 'value' in ts_point.metrics:
                        value = ts_point.metrics['value']
                        point_metrics = {k: v for k, v in ts_point.metrics.items() if k != 'value'}
                    else:
                        # Use first numeric metric as value
                        for k, v in ts_point.metrics.items():
                            if isinstance(v, (int, float)):
                                value = v
                                point_metrics = {kk: vv for kk, vv in ts_point.metrics.items() if kk != k}
                                break

                if value is None:
                    continue  # Skip points without values

                # Build time series document with hierarchical structure
                ts_metadata = TimeSeriesMetadata(
                    document_id=self.metadata.document_id,
                    timeseries_id=ts_id,
                    timestamp=ts_point.timestamp,
                    sequence=sequence,
                    test_timestamp=self.metadata.test_timestamp,
                    processing_timestamp=self.metadata.processing_timestamp,
                    os_vendor=self.metadata.os_vendor,
                    cloud_provider=self.metadata.cloud_provider,
                    instance_type=self.metadata.instance_type,
                    scenario_name=self.metadata.scenario_name,
                    iteration=self.metadata.iteration
                )

                ts_run = TimeSeriesRun(
                    run_key=run_key,
                    run_number=run.run_number,
                    status=run.status,
                    configuration=run.configuration,
                    benchmark_name=benchmark_name,
                    benchmark_description=benchmark_desc
                )

                ts_results = TimeSeriesResults(
                    run=ts_run,
                    value=value,
                    unit=unit,
                    point_metrics=point_metrics if point_metrics else None
                )

                ts_doc = TimeSeriesDocument(
                    metadata=ts_metadata,
                    test=self.test,
                    system_under_test=self.system_under_test,
                    results=ts_results
                )

                ts_docs.append(ts_doc)

        return ts_docs

    def validate(self) -> tuple[bool, List[str]]:
        """
        Validate document structure
        Returns: (is_valid, list_of_errors)
        """
        errors = []

        # Required fields
        if not self.metadata.document_id:
            errors.append("metadata.document_id is required")
        if not self.test.name:
            errors.append("test.name is required")
        if not self.results.status:
            errors.append("results.status is required")

        # Validate runs structure
        if self.results.runs:
            for run_key, run in self.results.runs.items():
                if not run_key.startswith("run_"):
                    errors.append(f"Invalid run key: {run_key}. Must start with 'run_'")

                # Validate timeseries has sequence keys
                if run.timeseries:
                    for ts_key in run.timeseries.keys():
                        if not ts_key.startswith("sequence_"):
                            errors.append(
                                f"Invalid sequence key in {run_key}.timeseries: {ts_key}. "
                                f"Must start with 'sequence_'"
                            )

        return (len(errors) == 0, errors)


# Utility functions

def create_run_key(run_number: int) -> str:
    """Generate standardized run key: run_1, run_2, etc."""
    return f"run_{run_number}"


def create_sequence_key(sequence: int) -> str:
    """Generate standardized sequence key: sequence_0, sequence_1, etc."""
    return f"sequence_{sequence}"


def parse_timestamp_key(timestamp_key: str) -> datetime:
    """Parse timestamp key back to datetime object"""
    return datetime.fromisoformat(timestamp_key.replace('Z', '+00:00'))


@dataclass
class TimeSeriesMetadata:
    """Metadata section for time series document"""
    document_id: str  # Parent document ID
    timeseries_id: str  # Unique ID for this time series point
    timestamp: str  # ISO 8601 timestamp for the data point
    sequence: int  # Sequence number within the run
    test_timestamp: Optional[str] = None  # When test was run
    processing_timestamp: Optional[str] = None  # When processed
    os_vendor: Optional[str] = None
    cloud_provider: Optional[str] = None
    instance_type: Optional[str] = None
    scenario_name: Optional[str] = None
    iteration: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class TimeSeriesRun:
    """Run details for time series document"""
    run_key: str  # e.g., "run_0"
    run_number: int  # 0, 1, 2, etc.
    status: str  # PASS, FAIL, etc.
    configuration: Optional[Dict[str, Any]] = None
    benchmark_name: Optional[str] = None  # For multi-benchmark tests
    benchmark_description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class TimeSeriesResults:
    """Results section for time series document"""
    run: TimeSeriesRun  # The run this point belongs to
    value: float  # Primary measurement value
    unit: str  # Unit of measurement (seconds, bops, MB/s, etc.)
    point_metrics: Optional[Dict[str, Any]] = None  # Point-specific extras

    def to_dict(self) -> Dict[str, Any]:
        result = {
            'run': self.run.to_dict(),
            'value': self.value,
            'unit': self.unit
        }
        if self.point_metrics:
            result['point_metrics'] = self.point_metrics
        return result


@dataclass
class TimeSeriesDocument:
    """
    Individual time series data point document for zathras-timeseries index.

    Maintains same top-level structure as ZathrasDocument (summary) for consistency:
    - metadata: Document identification and timestamps
    - test: Test information
    - system_under_test: Full SUT details (denormalized)
    - results: The actual data point with run context
    """
    metadata: TimeSeriesMetadata
    test: TestInfo
    system_under_test: SystemUnderTest
    results: TimeSeriesResults

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "metadata": self.metadata.to_dict(),
            "test": self.test.to_dict(),
            "system_under_test": self.system_under_test.to_dict(),
            "results": self.results.to_dict()
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string"""
        return json.dumps(self.to_dict(), indent=indent)


def validate_json_schema(document: Dict[str, Any]) -> tuple[bool, List[str]]:
    """
    Validate a dictionary against the expected schema
    Returns: (is_valid, list_of_errors)
    """
    errors = []

    # Check top-level sections
    required_sections = ['metadata', 'test', 'system_under_test', 'test_configuration', 'results']
    for section in required_sections:
        if section not in document:
            errors.append(f"Missing required section: {section}")

    # Check results.runs structure
    if 'results' in document and 'runs' in document['results']:
        runs = document['results']['runs']
        if not isinstance(runs, dict):
            errors.append("results.runs must be an object/dict, not an array")
        else:
            for run_key, run_data in runs.items():
                if not run_key.startswith("run_"):
                    errors.append(f"Invalid run key: {run_key}")

                # Check timeseries structure
                if 'timeseries' in run_data:
                    if not isinstance(run_data['timeseries'], dict):
                        errors.append(f"{run_key}.timeseries must be an object with timestamp keys")

    return (len(errors) == 0, errors)
