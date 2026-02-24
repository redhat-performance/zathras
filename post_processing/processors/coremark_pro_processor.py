"""
CoreMark Pro processor for Zathras results.

CoreMark Pro is a comprehensive multi-workload benchmark suite that tests various
aspects of processor performance including JPEG encoding, core algorithms, linear algebra,
loops, neural networks, parsing, radix sort, SHA hashing, and compression.

Expects results CSV with Start_Date and End_Date columns (ISO 8601). Timestamps
are required; missing or malformed timestamps raise ProcessorError.
"""

import re
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import logging

from .base_processor import BaseProcessor, ProcessorError
from ..schema import Run, TimeSeriesPoint, TimeSeriesSummary, create_run_key, create_sequence_key
from ..utils.parser_utils import read_file_content

logger = logging.getLogger(__name__)

# ISO 8601 pattern (e.g. 2026-02-13T20:18:29Z or with fractional seconds)
_ISO8601_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
)


def _validate_iso8601_timestamp(value: str, context: str) -> str:
    """Validate and return an ISO 8601 timestamp string. Raises ProcessorError if invalid."""
    if not value or not isinstance(value, str):
        raise ProcessorError(
            f"CoreMark Pro results require timestamps. {context} "
            "Start_Date and End_Date must be non-empty strings."
        )
    value = value.strip()
    if not value:
        raise ProcessorError(
            f"CoreMark Pro results require timestamps. {context} "
            "Start_Date and End_Date cannot be blank."
        )
    if not _ISO8601_PATTERN.match(value):
        raise ProcessorError(
            f"CoreMark Pro results require valid ISO 8601 timestamps. {context} "
            f"Got: {value!r}. Expected format: YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DDTHH:MM:SS.ffffffZ"
        )
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise ProcessorError(
            f"CoreMark Pro results require valid ISO 8601 timestamps. {context} "
            f"Cannot parse {value!r}: {e}"
        ) from e
    return value


class CoreMarkProProcessor(BaseProcessor):
    """Processor for CoreMark Pro comprehensive benchmark results."""

    def get_test_name(self) -> str:
        return "coremark_pro"

    def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Run]:
        """
        Parse CoreMark Pro runs into object-based structure.

        CoreMark Pro runs multiple workload tests (cjpeg, core, linear_alg, etc.)
        in a single execution, with metrics for multi-core, single-core, and scaling.

        Resolves CSV path via extracted_result["files"] (e.g. results_csv) when
        provided (demo/single-file style), else from extracted_result["extracted_path"]
        with results.csv directly in that directory or in a coremark_pro_* subdirectory.

        Returns:
            A dictionary of Run objects, keyed by run_key (typically just "run_0").
        """
        csv_file: Optional[Path] = None
        result_dir: Optional[Path] = None

        files = extracted_result.get("files") or {}
        if files.get("results_csv"):
            csv_file = Path(files["results_csv"])
            result_dir = csv_file.parent
        else:
            extracted_path = Path(extracted_result["extracted_path"])
            # Results file directly in extracted_path (e.g. tmp/coremark_pro/results.csv)
            direct_csv = extracted_path / "results.csv"
            if direct_csv.exists():
                csv_file = direct_csv
                result_dir = extracted_path
            else:
                result_dirs = [d for d in extracted_path.glob("coremark_pro_*") if d.is_dir()]
                if not result_dirs:
                    raise ProcessorError(
                        "CoreMark Pro results not found. Provide a CSV path in extracted_result['files']['results_csv'] "
                        f"or ensure results.csv exists in {extracted_path} or in a coremark_pro_* subdirectory."
                    )
                csv_file = result_dirs[0] / "results.csv"
                result_dir = result_dirs[0]

        if not csv_file or not csv_file.exists():
            raise ProcessorError(
                f"CoreMark Pro results CSV not found: {csv_file}. "
                "Ensure the file exists and includes Start_Date and End_Date columns (ISO 8601)."
            )

        run_data = self._parse_coremark_pro_csv(csv_file)

        # Build Run object
        run_objects = {}
        if run_data:
            run_objects[create_run_key(0)] = self._build_run_object(run_data)

        logger.info(f"Parsed CoreMark Pro: 1 run with {len(run_data.get('workloads', {}))} workloads")
        return run_objects

    def _parse_coremark_pro_csv(self, csv_file: Path) -> Dict[str, Any]:
        """
        Parse the CoreMark Pro results CSV file.

        Supports comma-delimited format with required Start_Date and End_Date columns:
        Test,Multi_iterations,Single_iterations,Scaling,Start_Date,End_Date
        cjpeg-rose7-preset,434.78,217.39,2.00,2026-02-13T20:18:29Z,2026-02-13T20:19:14Z
        ...
        Score,14498.47,7411.58,1.95,2026-02-13T20:18:29Z,2026-02-13T20:19:14Z

        Raises ProcessorError if timestamps are missing from the header, or if any
        data row has missing or malformed Start_Date/End_Date.
        """
        if not csv_file.exists():
            raise ProcessorError(
                f"CoreMark Pro results file not found: {csv_file}. "
                "Ensure the CSV exists and includes Start_Date and End_Date columns (ISO 8601)."
            )

        content = read_file_content(csv_file)
        lines = content.strip().split('\n')

        run_data = {
            "run_number": 0,
            "status": "PASS",
            "workloads": {},
            "timeseries": {},
            "overall_metrics": {},
            "configuration": {},
            "start_timestamp": None,
            "end_timestamp": None,
        }

        in_meta = False
        header_tokens: Optional[list] = None
        sequence = 0

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue

            # Parse metadata section
            if "# Test general meta start" in line_stripped:
                in_meta = True
                continue
            elif "# Test general meta end" in line_stripped:
                in_meta = False
                continue

            if in_meta:
                meta_match = re.match(r'#\s*([^:]+):\s*(.+)', line_stripped)
                if meta_match:
                    key = meta_match.group(1).strip().lower().replace(' ', '_')
                    value = meta_match.group(2).strip()
                    run_data["configuration"][key] = value
                continue

            # Header line: must be comma-delimited with Start_Date and End_Date
            if line_stripped.startswith("Test,") or (
                "Start_Date" in line_stripped and "End_Date" in line_stripped and "," in line_stripped
            ):
                tokens = [t.strip() for t in line_stripped.split(",")]
                if "Start_Date" in tokens and "End_Date" in tokens:
                    header_tokens = tokens
                    continue
                raise ProcessorError(
                    "CoreMark Pro results require timestamps. The CSV header must be comma-delimited "
                    "and include Start_Date and End_Date columns "
                    "(e.g. Test,Multi_iterations,Single_iterations,Scaling,Start_Date,End_Date)."
                )

            # Legacy colon-delimited header (no timestamps)
            if line_stripped.startswith("Test:") and "Start_Date" not in line_stripped:
                raise ProcessorError(
                    "CoreMark Pro results require timestamps. The CSV must use comma-delimited format "
                    "with Start_Date and End_Date columns. Colon-delimited format without timestamps is not supported."
                )

            if header_tokens is None:
                continue

            # Data rows: comma-delimited
            parts = [p.strip() for p in line_stripped.split(",")]
            if len(parts) < 6:
                continue

            # Map columns by header
            try:
                start_idx = header_tokens.index("Start_Date")
                end_idx = header_tokens.index("End_Date")
            except ValueError:
                raise ProcessorError(
                    "CoreMark Pro results require Start_Date and End_Date columns in the CSV header."
                )
            if start_idx >= len(parts) or end_idx >= len(parts):
                raise ProcessorError(
                    f"CoreMark Pro CSV row has too few columns for Start_Date/End_Date: {line_stripped!r}"
                )

            start_ts = _validate_iso8601_timestamp(
                parts[start_idx],
                f"Row {sequence + 1} ({parts[0]!r}):",
            )
            end_ts = _validate_iso8601_timestamp(
                parts[end_idx],
                f"Row {sequence + 1} ({parts[0]!r}):",
            )

            if run_data["start_timestamp"] is None:
                run_data["start_timestamp"] = start_ts
                run_data["end_timestamp"] = end_ts
            # Optionally ensure consistency across rows; for run-level we already have first row's timestamps

            workload_name = parts[0].strip()

            if workload_name == "Score":
                try:
                    run_data["overall_metrics"]["multicore_score"] = float(parts[1])
                    run_data["overall_metrics"]["singlecore_score"] = float(parts[2])
                    if len(parts) > 4 and parts[3]:
                        run_data["overall_metrics"]["scaling_factor"] = float(parts[3])
                except (ValueError, IndexError) as e:
                    raise ProcessorError(
                        f"CoreMark Pro CSV: invalid Score row: {line_stripped!r} - {e}"
                    ) from e
            else:
                try:
                    multi_iters = float(parts[1])
                    single_iters = float(parts[2])
                    scaling = float(parts[3]) if len(parts) > 4 and parts[3] else None

                    run_data["workloads"][workload_name] = {
                        "multicore_iterations_per_sec": multi_iters,
                        "singlecore_iterations_per_sec": single_iters,
                        "scaling_factor": scaling
                    }

                    seq_key = create_sequence_key(sequence)
                    run_data["timeseries"][seq_key] = {
                        "timestamp": start_ts,
                        "metrics": {
                            "workload_name": workload_name,
                            "multicore_iterations_per_sec": multi_iters,
                            "singlecore_iterations_per_sec": single_iters,
                            "scaling_factor": scaling
                        }
                    }
                    sequence += 1

                except (ValueError, IndexError) as e:
                    raise ProcessorError(
                        f"CoreMark Pro CSV: invalid workload row: {line_stripped!r} - {e}"
                    ) from e

        if header_tokens is None and not run_data["workloads"] and not run_data["overall_metrics"]:
            raise ProcessorError(
                "CoreMark Pro results require timestamps. No header line with "
                "Test,Multi_iterations,Single_iterations,Scaling,Start_Date,End_Date was found."
            )

        if not run_data["start_timestamp"] or not run_data["end_timestamp"]:
            raise ProcessorError(
                "CoreMark Pro results require timestamps. No data row with valid Start_Date and End_Date was found."
            )

        return run_data

    def _build_run_object(self, run_data: Dict[str, Any]) -> Run:
        """Convert raw run data dictionary to Run dataclass object.

        Uses start_timestamp/end_timestamp and per-sequence timestamps from the CSV.
        Raises ProcessorError if any timeseries point is missing a valid timestamp.
        """
        timeseries = {}
        if "timeseries" in run_data and run_data["timeseries"]:
            for seq_key, ts_data in run_data["timeseries"].items():
                ts = ts_data.get("timestamp")
                if not ts:
                    raise ProcessorError(
                        f"CoreMark Pro run timeseries point {seq_key} is missing a timestamp. "
                        "Timestamps must come from the CSV Start_Date/End_Date."
                    )
                _validate_iso8601_timestamp(ts, f"Timeseries {seq_key}:")
                timeseries[seq_key] = TimeSeriesPoint(
                    timestamp=ts,
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

        return Run(
            run_number=run_data.get("run_number", 0),
            status=run_data.get("status", "UNKNOWN"),
            metrics=all_metrics,
            configuration=run_data.get("configuration", {}),
            timeseries=timeseries if timeseries else None,
            timeseries_summary=ts_summary,
            start_time=run_data.get("start_timestamp"),
            end_time=run_data.get("end_timestamp"),
        )
