"""
Phoronix Test Suite processor for Zathras results.

Phoronix Test Suite (PTS) is a comprehensive Linux testing and benchmarking platform
that runs multiple subtests covering CPU, memory, I/O, and system performance.
"""

import re
from typing import Dict, Any
from datetime import datetime
from pathlib import Path
import logging
import statistics

from .base_processor import BaseProcessor
from ..schema import Run, TimeSeriesPoint, TimeSeriesSummary, create_run_key, create_sequence_key
from ..utils.parser_utils import read_file_content

logger = logging.getLogger(__name__)


class PhoronixProcessor(BaseProcessor):
    """Processor for Phoronix Test Suite benchmark results."""

    def get_test_name(self) -> str:
        return "phoronix"

    def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Run]:
        """
        Parse Phoronix runs into object-based structure.

        Phoronix runs multiple subtests (e.g., Hash, MMAP, Pipe, etc.) in a single
        execution and reports results in BOPs (Billion Operations Per Second).

        We'll treat this as a single run with:
        - Individual test metrics
        - Each subtest as a time series point (sequence-based)

        Returns:
            A dictionary of Run objects, keyed by run_key (typically just "run_0").
        """
        extracted_path = Path(extracted_result['extracted_path'])

        # Find the results.csv file (may be nested)
        csv_files = list(extracted_path.rglob("results.csv"))

        if not csv_files:
            logger.error(f"No results.csv found in {extracted_path}")
            return {}

        csv_file = csv_files[0]

        # Parse the CSV file
        run_data = self._parse_phoronix_csv(csv_file)

        # Build Run object
        run_objects = {}
        if run_data:
            run_objects[create_run_key(0)] = self._build_run_object(run_data)

        logger.info(f"Parsed Phoronix: 1 run with {len(run_data.get('subtests', {}))} subtests")
        return run_objects

    def _parse_phoronix_csv(self, csv_file: Path) -> Dict[str, Any]:
        """
        Parse the Phoronix results.csv file.

        Format:
        # Test general meta start
        # <metadata lines>
        # Test general meta end
        Test:BOPs
        Hash:919241.57
        MMAP:198.61
        ...
        """
        if not csv_file.exists():
            logger.warning(f"CSV file not found: {csv_file}")
            return {}

        content = read_file_content(csv_file)
        lines = content.strip().split('\n')

        run_data = {
            "run_number": 0,
            "status": "PASS",
            "subtests": {},
            "timeseries": {},
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
                meta_match = re.match(r'#\s*([^:]+):\s*(.+)', line)
                if meta_match:
                    key = meta_match.group(1).strip().lower().replace(' ', '_')
                    value = meta_match.group(2).strip()
                    run_data["configuration"][key] = value
                continue

            # Header line: Test:BOPs
            if line.startswith("Test:"):
                header_found = True
                # Extract unit from header
                parts = line.split(':')
                if len(parts) > 1:
                    run_data["configuration"]["unit"] = parts[1].strip()
                continue

            if not header_found:
                continue

            # Data lines: test_name:value
            parts = line.split(':')
            if len(parts) != 2:
                continue

            test_name = parts[0].strip()
            try:
                value = float(parts[1].strip())
            except ValueError:
                logger.warning(f"Failed to parse value for {test_name}: {parts[1]}")
                continue

            # Store subtest metric
            run_data["subtests"][test_name] = value

            # Create time series point for this subtest
            seq_key = create_sequence_key(sequence)
            run_data["timeseries"][seq_key] = {
                "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "metrics": {
                    "test_name": test_name,
                    "bops": value
                }
            }
            sequence += 1

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

        # Calculate time series summary using BOPs values
        ts_summary = None
        if timeseries:
            # Extract BOPs values for summary stats
            bops_values = []
            for ts_point in timeseries.values():
                if "bops" in ts_point.metrics:
                    bops_values.append(ts_point.metrics["bops"])

            if bops_values:
                ts_summary = TimeSeriesSummary(
                    mean=statistics.mean(bops_values),
                    median=statistics.median(bops_values),
                    min=min(bops_values),
                    max=max(bops_values),
                    stddev=statistics.stdev(bops_values) if len(bops_values) > 1 else 0.0,
                    count=len(bops_values)
                )

        # Flatten subtest metrics into top-level metrics with prefixes
        all_metrics = {}
        for test_name, bops_value in run_data.get("subtests", {}).items():
            # Sanitize test name for metric key (remove spaces, special chars)
            metric_key = re.sub(r'[^\w]+', '_', test_name).lower().strip('_') + "_bops"
            all_metrics[metric_key] = bops_value

        # Add overall statistics
        if run_data.get("subtests"):
            bops_values = list(run_data["subtests"].values())
            all_metrics["total_subtests"] = len(bops_values)
            all_metrics["mean_bops"] = statistics.mean(bops_values)
            all_metrics["median_bops"] = statistics.median(bops_values)
            all_metrics["min_bops"] = min(bops_values)
            all_metrics["max_bops"] = max(bops_values)

        # Create Run object
        return Run(
            run_number=run_data.get("run_number", 0),
            status=run_data.get("status", "UNKNOWN"),
            metrics=all_metrics,
            configuration=run_data.get("configuration", {}),
            timeseries=timeseries if timeseries else None,
            timeseries_summary=ts_summary
        )
