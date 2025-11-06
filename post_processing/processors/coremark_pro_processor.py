"""
CoreMark Pro processor for Zathras results.

CoreMark Pro is a comprehensive multi-workload benchmark suite that tests various
aspects of processor performance including JPEG encoding, core algorithms, linear algebra,
loops, neural networks, parsing, radix sort, SHA hashing, and compression.
"""

import re
from typing import Dict, Any
from datetime import datetime
from pathlib import Path
import logging

from .base_processor import BaseProcessor
from ..schema import Run, TimeSeriesPoint, TimeSeriesSummary, create_run_key, create_sequence_key
from ..utils.parser_utils import read_file_content

logger = logging.getLogger(__name__)


class CoreMarkProProcessor(BaseProcessor):
    """Processor for CoreMark Pro comprehensive benchmark results."""

    def get_test_name(self) -> str:
        return "coremark_pro"

    def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Run]:
        """
        Parse CoreMark Pro runs into object-based structure.

        CoreMark Pro runs multiple workload tests (cjpeg, core, linear_alg, etc.)
        in a single execution, with metrics for multi-core, single-core, and scaling.

        We'll treat this as a single run with:
        - Overall metrics (overall score)
        - Individual workload metrics as nested data
        - Workload-specific results as time series points (sequence-based)

        Returns:
            A dictionary of Run objects, keyed by run_key (typically just "run_0").
        """
        extracted_path = Path(extracted_result['extracted_path'])

        # The extracted_path points to the coremark_pro_* directory itself
        # Check if results.csv is directly in extracted_path
        csv_file = extracted_path / "results.csv"

        # If not, look for a coremark_pro_* subdirectory
        if not csv_file.exists():
            result_dirs = [d for d in extracted_path.glob("coremark_pro_*") if d.is_dir()]
            if not result_dirs:
                logger.error(f"results.csv not found in {extracted_path} and no coremark_pro_* subdirectory found")
                return {}
            csv_file = result_dirs[0] / "results.csv"

        # Parse the CSV file for metrics
        if not csv_file.exists():
            logger.error(f"results.csv not found: {csv_file}")
            return {}

        run_data = self._parse_coremark_pro_csv(csv_file)

        # Build Run object
        run_objects = {}
        if run_data:
            run_objects[create_run_key(0)] = self._build_run_object(run_data)

        logger.info(f"Parsed CoreMark Pro: 1 run with {len(run_data.get('workloads', {}))} workloads")
        return run_objects

    def _parse_coremark_pro_csv(self, csv_file: Path) -> Dict[str, Any]:
        """
        Parse the CoreMark Pro results.csv file.

        Format:
        # Test general meta start
        # <metadata lines>
        # Test general meta end
        Test:Multi iterations:Single Iterations:Scaling
        cjpeg-rose7-preset:1000.00:200.00:5.00
        core:12.14:2.34:5.19
        ...
        Score:35614.20:8064.91
        """
        if not csv_file.exists():
            logger.warning(f"CSV file not found: {csv_file}")
            return {}

        content = read_file_content(csv_file)
        lines = content.strip().split('\n')

        run_data = {
            "run_number": 0,
            "status": "PASS",  # CoreMark Pro doesn't explicitly report status
            "workloads": {},
            "timeseries": {},
            "overall_metrics": {},
            "configuration": {}
        }

        in_meta = False
        header_found = False
        sequence = 0

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Parse metadata section
            if "# Test general meta start" in line:
                in_meta = True
                continue
            elif "# Test general meta end" in line:
                in_meta = False
                continue

            if in_meta:
                # Extract configuration from metadata comments
                # Example: # Tuned: virtual-guest
                meta_match = re.match(r'#\s*([^:]+):\s*(.+)', line)
                if meta_match:
                    key = meta_match.group(1).strip().lower().replace(' ', '_')
                    value = meta_match.group(2).strip()
                    run_data["configuration"][key] = value
                continue

            # Header line
            if line.startswith("Test:Multi"):
                header_found = True
                continue

            if not header_found:
                continue

            # Data lines: workload_name:multi:single:scaling
            # Or: Score:multi:single
            parts = line.split(':')
            if len(parts) < 3:
                continue

            workload_name = parts[0].strip()

            if workload_name == "Score":
                # Overall score
                try:
                    run_data["overall_metrics"]["multicore_score"] = float(parts[1])
                    run_data["overall_metrics"]["singlecore_score"] = float(parts[2])
                    if len(parts) > 3 and parts[3]:
                        run_data["overall_metrics"]["scaling_factor"] = float(parts[3])
                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse Score line: {line} - {e}")
            else:
                # Individual workload
                try:
                    multi_iters = float(parts[1])
                    single_iters = float(parts[2])
                    scaling = float(parts[3]) if len(parts) > 3 else None

                    # Store workload metrics
                    run_data["workloads"][workload_name] = {
                        "multicore_iterations_per_sec": multi_iters,
                        "singlecore_iterations_per_sec": single_iters,
                        "scaling_factor": scaling
                    }

                    # Create time series point for this workload
                    # Use sequence number since all workloads run at roughly the same time
                    seq_key = create_sequence_key(sequence)
                    run_data["timeseries"][seq_key] = {
                        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "metrics": {
                            "workload_name": workload_name,
                            "multicore_iterations_per_sec": multi_iters,
                            "singlecore_iterations_per_sec": single_iters,
                            "scaling_factor": scaling
                        }
                    }
                    sequence += 1

                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse workload line: {line} - {e}")

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

        # Calculate time series summary
        ts_summary = None
        if timeseries:
            # Extract multicore iterations for summary stats
            multicore_values = []
            for ts_point in timeseries.values():
                if "multicore_iterations_per_sec" in ts_point.metrics:
                    multicore_values.append(ts_point.metrics["multicore_iterations_per_sec"])

            if multicore_values:
                import statistics
                ts_summary = TimeSeriesSummary(
                    mean=statistics.mean(multicore_values),
                    median=statistics.median(multicore_values),
                    min=min(multicore_values),
                    max=max(multicore_values),
                    stddev=statistics.stdev(multicore_values) if len(multicore_values) > 1 else 0.0,
                    count=len(multicore_values)
                )

        # Flatten workload metrics into top-level metrics with prefixes
        all_metrics = {}
        all_metrics.update(run_data.get("overall_metrics", {}))

        for workload_name, workload_metrics in run_data.get("workloads", {}).items():
            # Prefix workload-specific metrics to avoid name collisions
            for metric_name, value in workload_metrics.items():
                all_metrics[f"{workload_name}_{metric_name}"] = value

        # Create Run object
        return Run(
            run_number=run_data.get("run_number", 0),
            status=run_data.get("status", "UNKNOWN"),
            metrics=all_metrics,
            configuration=run_data.get("configuration", {}),
            timeseries=timeseries if timeseries else None,
            timeseries_summary=ts_summary
        )
