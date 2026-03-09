"""
Passmark PerformanceTest processor for Zathras results.

Passmark PerformanceTest is a comprehensive benchmark suite that tests CPU and memory
performance across various workloads including integer/floating point math, encryption,
compression, memory allocation, read/write, and more.
"""

import re
import yaml
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
import logging
import statistics

from .base_processor import BaseProcessor, ProcessorError
from ..schema import Run, TimeSeriesPoint, TimeSeriesSummary, create_run_key, create_sequence_key
from ..utils.parser_utils import read_file_content

logger = logging.getLogger(__name__)

# Passmark BaselineInfo.TimeStamp: 14 digits YYYYMMDDHHmmss
_PASSMARK_TS_PATTERN = re.compile(r"^\d{14}$")


def _validate_passmark_timestamp(value: Any, context: str) -> str:
    """Validate Passmark TimeStamp (14-digit YYYYMMDDHHmmss) and return ISO 8601 string. Raises ProcessorError if invalid."""
    if value is None:
        raise ProcessorError(
            f"Passmark results require timestamps. {context} "
            "BaselineInfo.TimeStamp must be present (14-digit format YYYYMMDDHHmmss)."
        )
    ts_str = str(value).strip()
    if not ts_str:
        raise ProcessorError(
            f"Passmark results require timestamps. {context} "
            "BaselineInfo.TimeStamp cannot be empty. Expected format: YYYYMMDDHHmmss."
        )
    if not _PASSMARK_TS_PATTERN.match(ts_str):
        raise ProcessorError(
            f"Passmark results require valid timestamps. {context} "
            f"Got: {value!r}. Expected format: 14 digits YYYYMMDDHHmmss (e.g. 20250918195935)."
        )
    try:
        dt = datetime(
            int(ts_str[0:4]), int(ts_str[4:6]), int(ts_str[6:8]),
            int(ts_str[8:10]), int(ts_str[10:12]), int(ts_str[12:14])
        )
    except ValueError as e:
        raise ProcessorError(
            f"Passmark results require valid timestamps. {context} "
            f"Cannot parse {value!r}: {e}"
        ) from e
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class PassmarkProcessor(BaseProcessor):
    """Processor for Passmark PerformanceTest benchmark results."""

    def get_test_name(self) -> str:
        return "passmark"

    def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Run]:
        """
        Parse Passmark runs into object-based structure.

        Passmark runs multiple test iterations (typically 5) and stores each in a
        separate YML file (results_all_1.yml, results_all_2.yml, etc.).

        Resolves result files via extracted_result['files']['results_yml'] (single path
        or list) for demo/single-file use, or via extracted_result['extracted_path'] with
        results_all_*.yml in that directory.

        We'll treat this as a single run with:
        - Aggregated metrics (averages across all iterations)
        - Individual iteration results as time series points (timestamps from BaselineInfo.TimeStamp).

        Returns:
            A dictionary of Run objects, keyed by run_key (typically just "run_0").
        """
        results_files: List[Path] = []
        files = extracted_result.get("files") or {}
        results_yml = files.get("results_yml")
        if results_yml is not None:
            if isinstance(results_yml, (list, tuple)):
                results_files = [Path(p) for p in results_yml]
            else:
                results_files = [Path(results_yml)]
            results_files = sorted(f for f in results_files if f.exists())
        else:
            extracted_path = extracted_result.get("extracted_path")
            if not extracted_path:
                raise ProcessorError(
                    "Passmark results require either files.results_yml (path or list of paths) "
                    "or extracted_path containing results_all_*.yml."
                )
            result_dir = Path(extracted_path)
            # Results may live directly in extracted_path (no test-specific subdirectory)
            results_files = sorted(result_dir.glob("results_all_*.yml"))

        if not results_files:
            loc = f"files.results_yml or {extracted_result.get('extracted_path', 'extracted_path')}"
            raise ProcessorError(
                f"Passmark results: no results_all_*.yml files found. "
                f"Provide valid path(s) in {loc} or ensure the directory contains results_all_*.yml."
            )

        # Parse all YML files (timestamp missing/invalid raises ProcessorError)
        iterations = []
        for yml_file in results_files:
            iteration_data = self._parse_passmark_yml(yml_file)
            if iteration_data:
                iterations.append(iteration_data)

        if not iterations:
            raise ProcessorError(
                "Passmark results: no valid iteration data found. "
                "Each YML must have a Results section and BaselineInfo.TimeStamp (14-digit YYYYMMDDHHmmss)."
            )

        # Build run with aggregated metrics and time series
        run_data = self._aggregate_iterations(iterations)

        # Build Run object
        run_objects = {}
        if run_data:
            run_objects[create_run_key(0)] = self._build_run_object(run_data)

        logger.info(f"Parsed Passmark: 1 run with {len(iterations)} iterations")
        return run_objects

    def _parse_passmark_yml(self, yml_file: Path) -> Optional[Dict[str, Any]]:
        """
        Parse a single Passmark results YML file.

        Requires BaselineInfo.TimeStamp (14-digit YYYYMMDDHHmmss). Raises ProcessorError
        if timestamp is missing or malformed.

        Structure:
        BaselineInfo:
          WebDBID: -1
          TimeStamp: 20250918195935
        Version:
          Major: 11
          Minor: 0
        Results:
          NumTestProcesses: 8
          CPU_INTEGER_MATH: 35167.01
          ...
        SystemInformation:
          OSName: Red Hat Enterprise Linux 9.6
          ...
        """
        if not yml_file.exists():
            logger.warning(f"YML file not found: {yml_file}")
            return None

        try:
            content = read_file_content(yml_file)
            data = yaml.safe_load(content)

            if not data or 'Results' not in data:
                logger.warning(f"No Results section in {yml_file}")
                return None

            results = data['Results']
            context = f"File {yml_file.name}:"

            # Require BaselineInfo.TimeStamp; validate and convert to ISO 8601
            raw_ts = None
            if 'BaselineInfo' in data and isinstance(data['BaselineInfo'], dict):
                raw_ts = data['BaselineInfo'].get('TimeStamp')
            timestamp = _validate_passmark_timestamp(raw_ts, context)

            return {
                'timestamp': timestamp,
                'metrics': results,
                'version': data.get('Version', {}),
                'system_info': data.get('SystemInformation', {})
            }

        except ProcessorError:
            raise
        except Exception as e:
            logger.error(f"Failed to parse {yml_file}: {e}")
            return None

    def _aggregate_iterations(self, iterations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggregate multiple iterations into a single run with time series.

        Calculates mean, min, max for each metric across all iterations,
        and creates time series points for each iteration.
        """
        run_data = {
            "run_number": 0,
            "status": "PASS",
            "metrics": {},
            "timeseries": {},
            "configuration": {}
        }

        # Collect all metric values across iterations
        metric_values = {}

        for iteration in iterations:
            for metric_name, value in iteration['metrics'].items():
                if isinstance(value, (int, float)) and metric_name not in ['NumTestProcesses']:
                    if metric_name not in metric_values:
                        metric_values[metric_name] = []
                    metric_values[metric_name].append(float(value))

        # Calculate aggregated metrics
        for metric_name, values in metric_values.items():
            run_data["metrics"][f"{metric_name}_mean"] = statistics.mean(values)
            run_data["metrics"][f"{metric_name}_min"] = min(values)
            run_data["metrics"][f"{metric_name}_max"] = max(values)
            if len(values) > 1:
                run_data["metrics"][f"{metric_name}_stddev"] = statistics.stdev(values)

        # Create time series points for each iteration
        for i, iteration in enumerate(iterations):
            seq_key = create_sequence_key(i)

            # Extract only numeric metrics for this iteration
            iteration_metrics = {}
            for metric_name, value in iteration['metrics'].items():
                if isinstance(value, (int, float)) and metric_name not in ['NumTestProcesses']:
                    iteration_metrics[metric_name] = float(value)

            run_data["timeseries"][seq_key] = {
                "timestamp": iteration['timestamp'],
                "metrics": iteration_metrics
            }

        # Add configuration from first iteration
        if iterations:
            first_iteration = iterations[0]
            if 'NumTestProcesses' in first_iteration['metrics']:
                num_processes = first_iteration['metrics']['NumTestProcesses']
                run_data["configuration"]["num_test_processes"] = num_processes

            if 'version' in first_iteration:
                version = first_iteration['version']
                if isinstance(version, dict):
                    major = version.get('Major', 0)
                    minor = version.get('Minor', 0)
                    build = version.get('Build', 0)
                    run_data["configuration"]["version"] = f"{major}.{minor}.{build}"

        return run_data

    def _build_run_object(self, run_data: Dict[str, Any]) -> Run:
        """Convert raw run data dictionary to Run dataclass object. Requires valid timestamp per timeseries point."""

        # Convert timeseries dictionary to TimeSeriesPoint objects (timestamps from YML BaselineInfo.TimeStamp)
        timeseries = {}
        if "timeseries" in run_data and run_data["timeseries"]:
            for seq_key, ts_data in run_data["timeseries"].items():
                ts = ts_data.get("timestamp")
                if not ts:
                    raise ProcessorError(
                        f"Passmark run is missing timestamp for {seq_key}. "
                        "Timestamps must come from BaselineInfo.TimeStamp in each results_all_*.yml."
                    )
                timeseries[seq_key] = TimeSeriesPoint(
                    timestamp=ts,
                    metrics=ts_data.get("metrics", {})
                )

        # Calculate time series summary using SUMM_CPU_mean as the primary metric
        ts_summary = None
        if timeseries:
            # Extract SUMM_CPU values for summary stats
            summ_cpu_values = []
            for ts_point in timeseries.values():
                if "SUMM_CPU" in ts_point.metrics:
                    summ_cpu_values.append(ts_point.metrics["SUMM_CPU"])

            if summ_cpu_values:
                ts_summary = TimeSeriesSummary(
                    mean=statistics.mean(summ_cpu_values),
                    median=statistics.median(summ_cpu_values),
                    min=min(summ_cpu_values),
                    max=max(summ_cpu_values),
                    stddev=statistics.stdev(summ_cpu_values) if len(summ_cpu_values) > 1 else 0.0,
                    count=len(summ_cpu_values)
                )

        # Create Run object
        return Run(
            run_number=run_data.get("run_number", 0),
            status=run_data.get("status", "UNKNOWN"),
            metrics=run_data.get("metrics", {}),
            configuration=run_data.get("configuration", {}),
            timeseries=timeseries if timeseries else None,
            timeseries_summary=ts_summary
        )
