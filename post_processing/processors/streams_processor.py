"""
STREAMS Memory Bandwidth Benchmark Processor

Processes STREAMS results including:
- Multiple optimization levels (O2, O3)
- Multiple array sizes (266240k, 532480k, 1064960k)
- Four operations: Copy, Scale, Add, Triad
- Multiple iterations per configuration
"""

import re
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import logging

from .base_processor import BaseProcessor
from ..schema import Run, TimeSeriesPoint, create_run_key, create_sequence_key

logger = logging.getLogger(__name__)


class StreamsProcessor(BaseProcessor):
    """Processor for STREAMS memory bandwidth benchmark results."""

    def get_test_name(self) -> str:
        return "streams"

    def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse STREAMS runs into object-based structure

        Returns:
            {
                "run_1": {  # O2 optimization
                    "optimization_level": "O2",
                    "metrics": {...},
                    "timeseries": {
                        "sequence_0": {...},
                        ...
                    }
                },
                "run_2": {  # O3 optimization
                    "optimization_level": "O3",
                    "metrics": {...},
                    "timeseries": {...}
                }
            }
        """
        result_dir = Path(extracted_result['extracted_path'])

        # Find the streams results directory
        streams_dirs = list(result_dir.glob("streams_*"))
        if not streams_dirs:
            logger.warning(f"No streams_* directory found in {result_dir}")
            return {}

        streams_dir = streams_dirs[0]

        # Parse the CSV summary file
        csv_file = streams_dir / "results_streams.csv"
        runs = self._parse_streams_csv(csv_file)

        # Parse detailed results from individual run directories
        results_dir = streams_dir / "streams_results"
        if results_dir.exists():
            self._enrich_runs_with_detailed_results(runs, results_dir)

        # Convert dictionaries to Run objects
        run_objects = {}
        for run_key, run_data in runs.items():
            run_objects[run_key] = self._build_run_object(run_data)

        logger.info(f"Parsed {len(run_objects)} STREAMS runs")
        return run_objects

    def _parse_streams_csv(self, csv_file: Path) -> Dict[str, Any]:
        """Parse the results_streams.csv summary file."""
        runs = {}

        if not csv_file.exists():
            logger.warning(f"CSV file not found: {csv_file}")
            return runs

        with open(csv_file, 'r') as f:
            lines = f.readlines()

        current_opt_level = None
        run_number = 0
        array_sizes = []

        for line in lines:
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Extract optimization level from comments
            if line.startswith('#') and "Optimization level:" in line:
                opt_match = re.search(r'O(\d+)', line)
                if opt_match:
                    current_opt_level = f"O{opt_match.group(1)}"
                continue

            # Skip other comments
            if line.startswith('#'):
                continue

            # Parse socket info (skip)
            if "Socket" in line:
                continue

            # Parse array sizes
            if "Array sizes:" in line:
                array_sizes = line.split(':')[1:]
                continue

            # Parse operation results (Copy, Scale, Add, Triad)
            if ':' in line:
                parts = line.split(':')
                if len(parts) >= 2:
                    operation = parts[0].strip()

                    # Skip if not one of the 4 STREAMS operations
                    if operation not in ['Copy', 'Scale', 'Add', 'Triad']:
                        continue

                    values = [v.strip() for v in parts[1:]]

                    # Create a run for this optimization level if needed
                    run_key = create_run_key(run_number)
                    if run_key not in runs:
                        runs[run_key] = {
                            "run_number": run_number,
                            "optimization_level": current_opt_level or "unknown",
                            "array_sizes": array_sizes.copy(),
                            "metrics": {},
                            "timeseries": {}
                        }

                    # Store results for each array size
                    for idx, value in enumerate(values):
                        if not value:
                            continue

                        array_size = array_sizes[idx] if idx < len(array_sizes) else f"size_{idx}"
                        metric_name = f"{operation.lower()}_{array_size}_mb_per_sec"

                        try:
                            runs[run_key]["metrics"][metric_name] = float(value)
                        except ValueError:
                            msg = f"Failed to parse value '{value}' for {operation} at array size {array_size}"
                            logger.warning(msg)

            # Check if we've completed a run (empty line after all operations)
            if line == '' and current_opt_level and run_key in runs:
                if len(runs[run_key]["metrics"]) > 0:
                    run_number += 1

        # If we ended without an empty line, still count the last run
        if runs and run_key in runs and len(runs[run_key]["metrics"]) > 0:
            # Already counted
            pass
        elif current_opt_level and run_key in runs:
            # Count the final run
            run_number += 1

        return runs

    def _enrich_runs_with_detailed_results(self, runs: Dict[str, Any], results_dir: Path):
        """Enrich runs with detailed results from individual iteration files."""

        # Map optimization levels to run keys
        opt_to_run = {}
        for run_key, run_data in runs.items():
            opt_level = run_data.get("optimization_level", "unknown")
            opt_to_run[opt_level] = run_key

        # Find result directories for each optimization level
        for opt_dir in sorted(results_dir.glob("results_streams_*")):
            # Extract optimization level from directory name (e.g., -O2, -O3)
            opt_match = re.search(r'-O(\d+)', opt_dir.name)
            if not opt_match:
                continue

            opt_level = f"O{opt_match.group(1)}"
            run_key = opt_to_run.get(opt_level)

            if not run_key or run_key not in runs:
                continue

            # Parse individual iteration files
            sequence = 0
            for result_file in sorted(opt_dir.glob("stream.*.out.*")):
                data = self._parse_individual_stream_output(result_file)
                if data:
                    # Add as a time series point
                    seq_key = create_sequence_key(sequence)

                    metrics = {}
                    for op in ['Copy', 'Scale', 'Add', 'Triad']:
                        if op in data:
                            metrics[f"{op.lower()}_{data['array_size']}_mb_per_sec"] = data[op]

                    if metrics:  # Only add if we have metrics
                        runs[run_key]["timeseries"][seq_key] = {
                            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "metrics": metrics
                        }
                        sequence += 1

    def _parse_individual_stream_output(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Parse an individual STREAMS output file."""

        # Extract array size and iteration from filename
        # e.g., stream.266240k.out.threads_8.numb_sockets_1_iter_1
        filename = file_path.name
        array_match = re.search(r'stream\.(\d+k)\.', filename)
        threads_match = re.search(r'threads_(\d+)', filename)
        iter_match = re.search(r'iter_(\d+)', filename)

        if not array_match:
            return None

        array_size = array_match.group(1)
        threads = int(threads_match.group(1)) if threads_match else 0
        iteration = int(iter_match.group(1)) if iter_match else 0

        # Parse the file content for operation results
        results = {
            'array_size': array_size,
            'threads': threads,
            'iteration': iteration
        }

        try:
            with open(file_path, 'r') as f:
                for line in f:
                    # Look for operation results
                    # Format: Copy:          103794.6     0.044949     0.042026     0.062490
                    if ':' in line and any(op in line for op in ['Copy', 'Scale', 'Add', 'Triad']):
                        parts = line.split()
                        if len(parts) >= 2:
                            operation = parts[0].rstrip(':')
                            try:
                                bandwidth = float(parts[1])
                                results[operation] = bandwidth
                            except (ValueError, IndexError):
                                continue
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return None

        return results

    def _build_run_object(self, run_data: Dict[str, Any]) -> Run:
        """Convert raw run data dictionary to Run dataclass object."""

        # Convert timeseries dictionary to TimeSeriesPoint objects
        timeseries = {}
        if "timeseries" in run_data:
            for seq_key, ts_data in run_data["timeseries"].items():
                timeseries[seq_key] = TimeSeriesPoint(
                    timestamp=ts_data.get("timestamp", datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")),
                    metrics=ts_data.get("metrics", {})
                )

        # Build configuration dictionary
        config = {
            "optimization_level": run_data.get("optimization_level", "unknown"),
            "array_sizes": run_data.get("array_sizes", [])
        }

        # Create Run object
        return Run(
            run_number=run_data.get("run_number", 0),
            status="PASS",  # STREAMS doesn't provide explicit status
            metrics=run_data.get("metrics", {}),
            configuration=config,
            timeseries=timeseries if timeseries else None,
            timeseries_summary=None  # We could calculate this if needed
        )
