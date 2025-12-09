"""
Passmark PerformanceTest processor for Zathras results.

Passmark PerformanceTest is a comprehensive benchmark suite that tests CPU and memory
performance across various workloads including integer/floating point math, encryption,
compression, memory allocation, read/write, and more.
"""

import yaml
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
import logging
import statistics

from .base_processor import BaseProcessor
from ..schema import Run, TimeSeriesPoint, TimeSeriesSummary, create_run_key, create_sequence_key
from ..utils.parser_utils import read_file_content

logger = logging.getLogger(__name__)


class PassmarkProcessor(BaseProcessor):
    """Processor for Passmark PerformanceTest benchmark results."""

    def get_test_name(self) -> str:
        return "passmark"

    def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Run]:
        """
        Parse Passmark runs into object-based structure.

        Passmark runs multiple test iterations (typically 5) and stores each in a
        separate YML file (results_all_1.yml, results_all_2.yml, etc.).

        We'll treat this as a single run with:
        - Aggregated metrics (averages across all iterations)
        - Individual iteration results as time series points

        Returns:
            A dictionary of Run objects, keyed by run_key (typically just "run_0").
        """
        extracted_path = Path(extracted_result['extracted_path'])

        # The extracted_path points to the passmark_* directory itself
        # Find all results_all_*.yml files
        results_files = sorted(extracted_path.glob("results_all_*.yml"))

        if not results_files:
            logger.error(f"No results_all_*.yml files found in {extracted_path}")
            return {}

        # Parse all YML files
        iterations = []
        for yml_file in results_files:
            iteration_data = self._parse_passmark_yml(yml_file)
            if iteration_data:
                iterations.append(iteration_data)

        if not iterations:
            logger.error("No valid iteration data found")
            return {}

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

            # Extract timestamp if available
            timestamp = None
            if 'BaselineInfo' in data and 'TimeStamp' in data['BaselineInfo']:
                ts_str = str(data['BaselineInfo']['TimeStamp'])
                # Format: 20250918195935 -> 2025-09-18T19:59:35Z
                if len(ts_str) == 14:
                    timestamp = (
                        f"{ts_str[0:4]}-{ts_str[4:6]}-{ts_str[6:8]}T"
                        f"{ts_str[8:10]}:{ts_str[10:12]}:{ts_str[12:14]}Z"
                    )

            return {
                'timestamp': timestamp or datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                'metrics': results,
                'version': data.get('Version', {}),
                'system_info': data.get('SystemInformation', {})
            }

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
        """Convert raw run data dictionary to Run dataclass object."""

        # Convert timeseries dictionary to TimeSeriesPoint objects
        timeseries = {}
        if "timeseries" in run_data and run_data["timeseries"]:
            for seq_key, ts_data in run_data["timeseries"].items():
                timeseries[seq_key] = TimeSeriesPoint(
                    timestamp=ts_data.get("timestamp", datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")),
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
