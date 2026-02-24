"""
STREAMS Memory Bandwidth Benchmark Processor

Processes STREAMS results including:
- Multiple optimization levels (O2, O3)
- Multiple array sizes (266240k, 532480k, 1064960k)
- Four operations: Copy, Scale, Add, Triad
- Multiple iterations per configuration
"""

import re
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from pathlib import Path
import logging

from .base_processor import BaseProcessor, ProcessorError
from ..schema import Run, TimeSeriesPoint, create_run_key, create_sequence_key

logger = logging.getLogger(__name__)

# ISO 8601 pattern (e.g. 2026-02-04T00:19:56Z or with fractional seconds)
_ISO8601_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
)


def _validate_iso8601_timestamp(value: str, context: str) -> str:
    """Validate and return an ISO 8601 timestamp string. Raises ProcessorError if invalid."""
    if not value or not isinstance(value, str):
        raise ProcessorError(
            f"STREAMS results require timestamps. {context} "
            "Start_Date and End_Date must be non-empty strings."
        )
    value = value.strip()
    if not value:
        raise ProcessorError(
            f"STREAMS results require timestamps. {context} "
            "Start_Date and End_Date cannot be blank."
        )
    if not _ISO8601_PATTERN.match(value):
        raise ProcessorError(
            f"STREAMS results require valid ISO 8601 timestamps. {context} "
            f"Got: {value!r}. Expected format: YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DDTHH:MM:SS.ffffffZ"
        )
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise ProcessorError(
            f"STREAMS results require valid ISO 8601 timestamps. {context} "
            f"Cannot parse {value!r}: {e}"
        ) from e
    return value


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
        # Resolve CSV path: direct file (demo/style like tmp/coremark) or from extracted_path
        csv_file: Optional[Path] = None
        streams_dir: Optional[Path] = None

        files = extracted_result.get("files") or {}
        if files.get("results_streams_csv"):
            csv_file = Path(files["results_streams_csv"])
            streams_dir = csv_file.parent
        else:
            result_dir = Path(extracted_result["extracted_path"])
            # CSV in result_dir directly (e.g. tmp/streams/results_streams.csv) or in streams_*
            direct_csv = result_dir / "results_streams.csv"
            if direct_csv.exists():
                csv_file = direct_csv
                streams_dir = result_dir
            else:
                streams_dirs = list(result_dir.glob("streams_*"))
                if not streams_dirs:
                    logger.warning(f"No results_streams.csv or streams_* directory found in {result_dir}")
                    return {}
                streams_dir = streams_dirs[0]
                csv_file = streams_dir / "results_streams.csv"

        if not csv_file or not csv_file.exists():
            logger.warning(f"CSV file not found: {csv_file}")
            return {}

        runs = self._parse_streams_csv(csv_file)

        # Parse detailed results from individual run directories (if present)
        if streams_dir:
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
        """Parse the results_streams.csv summary file.

        Requires comma-delimited format with Start_Date and End_Date columns
        (e.g. "Array sizes,16384k,32768k,65536k,Start_Date,End_Date").
        Raises ProcessorError if timestamps are missing or malformed.
        """
        runs = {}

        if not csv_file.exists():
            logger.warning(f"CSV file not found: {csv_file}")
            return runs

        with open(csv_file, 'r') as f:
            lines = f.readlines()

        current_opt_level = None
        run_number = 0
        array_sizes: List[str] = []
        csv_has_timestamps = False
        run_key = None

        for line in lines:
            line_stripped = line.strip()

            # Skip empty lines
            if not line_stripped:
                # End of run block
                if current_opt_level and run_key and run_key in runs and len(runs[run_key]["metrics"]) > 0:
                    run_number += 1
                continue

            # Extract optimization level from comments
            if line_stripped.startswith('#') and "Optimization level:" in line_stripped:
                opt_match = re.search(r'O(\d+)', line_stripped)
                if opt_match:
                    current_opt_level = f"O{opt_match.group(1)}"
                continue

            # Skip other comments
            if line_stripped.startswith('#'):
                continue

            # Parse socket info (skip)
            if "Socket" in line_stripped:
                continue

            # Parse array sizes line (comma-delimited with Start_Date, End_Date)
            if line_stripped.startswith("Array sizes"):
                if "," in line_stripped:
                    tokens = [t.strip() for t in line_stripped.split(",")]
                    if len(tokens) >= 3 and tokens[-2] == "Start_Date" and tokens[-1] == "End_Date":
                        # First column is "Array sizes", then array size names, then Start_Date, End_Date
                        array_sizes = tokens[1:-2]
                        csv_has_timestamps = True
                    else:
                        raise ProcessorError(
                            "STREAMS results require timestamps. The CSV header line starting with "
                            "'Array sizes' must be comma-delimited and include Start_Date and End_Date "
                            "as the last two columns (e.g. 'Array sizes,16384k,32768k,65536k,Start_Date,End_Date')."
                        )
                else:
                    raise ProcessorError(
                        "STREAMS results require timestamps. The CSV must use comma-delimited format "
                        "with a header line like 'Array sizes,16384k,...,Start_Date,End_Date'. "
                        "Colon-delimited format without timestamps is not supported."
                    )
                continue

            # Parse operation results: comma-delimited "Copy,val1,val2,...,Start_Date,End_Date"
            if csv_has_timestamps and array_sizes:
                parts = [p.strip() for p in line_stripped.split(",")]
                if len(parts) >= 3 and parts[0] in ['Copy', 'Scale', 'Add', 'Triad']:
                    operation = parts[0]
                    # Last two columns are Start_Date, End_Date; rest are values per array size
                    n_sizes = len(array_sizes)
                    if len(parts) != n_sizes + 3:
                        raise ProcessorError(
                            f"STREAMS CSV row has wrong column count. Expected {n_sizes} array size values "
                            f"plus Start_Date and End_Date (got {len(parts)} columns for operation {operation})."
                        )
                    value_strs = parts[1 : 1 + n_sizes]
                    start_ts = parts[-2]
                    end_ts = parts[-1]

                    start_timestamp = _validate_iso8601_timestamp(
                        start_ts,
                        f"Run {run_number + 1}, {operation} row:"
                    )
                    end_timestamp = _validate_iso8601_timestamp(
                        end_ts,
                        f"Run {run_number + 1}, {operation} row:"
                    )

                    run_key = create_run_key(run_number)
                    if run_key not in runs:
                        runs[run_key] = {
                            "run_number": run_number,
                            "optimization_level": current_opt_level or "unknown",
                            "array_sizes": array_sizes.copy(),
                            "metrics": {},
                            "timeseries": {},
                            "start_timestamp": start_timestamp,
                            "end_timestamp": end_timestamp,
                        }
                    else:
                        # All rows in same run must have same timestamps; validate consistency
                        if runs[run_key]["start_timestamp"] != start_timestamp or runs[run_key]["end_timestamp"] != end_timestamp:
                            raise ProcessorError(
                                f"STREAMS CSV run {run_number + 1}: Start_Date/End_Date must be the same "
                                "for all rows (Copy, Scale, Add, Triad) in the same run."
                            )

                    for idx, value in enumerate(value_strs):
                        if not value:
                            continue
                        array_size = array_sizes[idx] if idx < len(array_sizes) else f"size_{idx}"
                        metric_name = f"{operation.lower()}_{array_size}_mb_per_sec"
                        try:
                            runs[run_key]["metrics"][metric_name] = float(value)
                        except ValueError:
                            raise ProcessorError(
                                f"STREAMS CSV: invalid numeric value '{value}' for {operation} "
                                f"at array size {array_size} (run {run_number + 1})."
                            )
                continue

            # Legacy colon-delimited line (no timestamps) -> not supported
            if ':' in line_stripped and line_stripped.split(':')[0].strip() in ['Copy', 'Scale', 'Add', 'Triad']:
                raise ProcessorError(
                    "STREAMS results require timestamps. The CSV must include Start_Date and End_Date columns "
                    "in comma-delimited format. This file appears to use colon-delimited format without timestamps."
                )

        # Require that we had timestamped format and every run has timestamps
        if not csv_has_timestamps and runs:
            raise ProcessorError(
                "STREAMS results require timestamps. No header line with 'Array sizes,...,Start_Date,End_Date' was found."
            )
        for rk, rdata in runs.items():
            if not rdata.get("start_timestamp") or not rdata.get("end_timestamp"):
                raise ProcessorError(
                    f"STREAMS results require timestamps. Run {rdata.get('run_number', rk)} is missing "
                    "Start_Date or End_Date. Ensure every data row includes valid ISO 8601 timestamps."
                )

        return runs

    def _enrich_runs_with_detailed_results(self, runs: Dict[str, Any], results_dir: Path):
        """Enrich runs with detailed results from individual iteration files.

        Timestamps for each sequence are interpolated between the run's
        start_timestamp and end_timestamp from the CSV.
        """
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

            run_data = runs[run_key]
            start_ts = run_data.get("start_timestamp")
            end_ts = run_data.get("end_timestamp")
            if not start_ts or not end_ts:
                raise ProcessorError(
                    f"STREAMS run {run_key} is missing start_timestamp or end_timestamp; "
                    "cannot enrich with detailed results."
                )

            # Collect all iteration data first to know count for interpolation
            iteration_results: List[Dict[str, Any]] = []
            for result_file in sorted(opt_dir.glob("stream.*.out.*")):
                data = self._parse_individual_stream_output(result_file)
                if data:
                    metrics = {}
                    for op in ['Copy', 'Scale', 'Add', 'Triad']:
                        if op in data:
                            metrics[f"{op.lower()}_{data['array_size']}_mb_per_sec"] = data[op]
                    if metrics:
                        iteration_results.append({"metrics": metrics})

            # Assign interpolated timestamps between start_timestamp and end_timestamp
            n = len(iteration_results)
            start_dt = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
            for sequence, item in enumerate(iteration_results):
                if n <= 1:
                    ts_str = start_ts
                else:
                    frac = sequence / (n - 1)
                    delta_sec = (end_dt - start_dt).total_seconds() * frac
                    point_dt = start_dt + timedelta(seconds=delta_sec)
                    ts_str = point_dt.strftime("%Y-%m-%dT%H:%M:%S") + (
                        f".{point_dt.microsecond:06d}".rstrip("0").rstrip(".") or ""
                    ) + "Z"
                seq_key = create_sequence_key(sequence)
                runs[run_key]["timeseries"][seq_key] = {"timestamp": ts_str, "metrics": item["metrics"]}

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
        """Convert raw run data dictionary to Run dataclass object.

        Uses start_timestamp/end_timestamp from the CSV. If there are no
        detailed timeseries points, creates one point with start_timestamp.
        Raises ProcessorError if any timeseries point is missing a valid timestamp.
        """
        timeseries = {}
        if run_data.get("timeseries"):
            for seq_key, ts_data in run_data["timeseries"].items():
                ts = ts_data.get("timestamp")
                if not ts:
                    raise ProcessorError(
                        f"STREAMS run {run_data.get('run_number')} timeseries point {seq_key} is missing "
                        "a timestamp. Timestamps must come from the CSV Start_Date/End_Date or be interpolated."
                    )
                _validate_iso8601_timestamp(ts, f"Run {run_data.get('run_number')}, {seq_key}:")
                timeseries[seq_key] = TimeSeriesPoint(
                    timestamp=ts,
                    metrics=ts_data.get("metrics", {}),
                )
        else:
            # No detailed results: create one timeseries point from CSV metrics and start_timestamp
            start_ts = run_data.get("start_timestamp")
            end_ts = run_data.get("end_timestamp")
            if not start_ts or not end_ts:
                raise ProcessorError(
                    f"STREAMS run {run_data.get('run_number')} has no timeseries and is missing "
                    "start_timestamp or end_timestamp from the CSV."
                )
            _validate_iso8601_timestamp(start_ts, f"Run {run_data.get('run_number')}:")
            timeseries[create_sequence_key(0)] = TimeSeriesPoint(
                timestamp=start_ts,
                metrics=run_data.get("metrics", {}).copy(),
            )

        config = {
            "optimization_level": run_data.get("optimization_level", "unknown"),
            "array_sizes": run_data.get("array_sizes", []),
        }

        return Run(
            run_number=run_data.get("run_number", 0),
            status="PASS",
            metrics=run_data.get("metrics", {}),
            configuration=config,
            timeseries=timeseries,
            timeseries_summary=None,
        )
