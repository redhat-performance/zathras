import csv
import io
import re
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import logging

from .base_processor import BaseProcessor, ProcessorError
from ..schema import Run, PrimaryMetric, TimeSeriesPoint, create_run_key, create_sequence_key
from ..utils.parser_utils import (
    parse_version_file,
    read_file_content,
)

logger = logging.getLogger(__name__)

# ISO 8601 pattern (e.g. 2026-02-26T03:21:32Z or with fractional seconds)
_ISO8601_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
)


def _validate_iso8601_timestamp(value: str, context: str = "") -> str:
    """Validate and return an ISO 8601 timestamp string. Raises ProcessorError if invalid."""
    if not value or not isinstance(value, str):
        raise ProcessorError(
            f"SPEC CPU 2017 results require timestamps. {context} "
            "Start_Date and End_Date must be non-empty strings."
        )
    value = value.strip()
    if not value:
        raise ProcessorError(
            f"SPEC CPU 2017 results require timestamps. {context} "
            "Start_Date and End_Date cannot be blank."
        )
    if not _ISO8601_PATTERN.match(value):
        raise ProcessorError(
            f"SPEC CPU 2017 results require valid ISO 8601 timestamps. {context} "
            f"Got: {value!r}. Expected format: YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DDTHH:MM:SS.ffffffZ"
        )
    try:
        from datetime import datetime
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise ProcessorError(
            f"SPEC CPU 2017 results require valid ISO 8601 timestamps. {context} "
            f"Cannot parse {value!r}: {e}"
        ) from e
    return value


class SpecCPU2017Processor(BaseProcessor):
    """
    Processor for SPEC CPU 2017 benchmark results.

    SPEC CPU 2017 has two independent test suites:
    - Integer Speed (intspeed): 10 benchmarks
    - Floating Point Speed (fpspeed): 13 benchmarks

    This processor creates one document with two runs (one per suite).
    """

    def get_test_name(self) -> str:
        return "speccpu2017"

    def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse SPEC CPU 2017 runs into object-based structure.

        Returns:
            {
                "run_0": {  # Integer suite
                    "run_number": 0,
                    "status": "PASS",
                    "metrics": {...},
                    "configuration": {...}
                },
                "run_1": {  # Floating point suite
                    "run_number": 1,
                    "status": "PASS",
                    "metrics": {...},
                    "configuration": {...}
                }
            }
        """
        files = extracted_result.get("files") or {}
        result_dir = Path(extracted_result.get("extracted_path") or ".")

        intrate_csv = None
        fprate_csv = None
        intspeed_csv = None
        fpspeed_csv = None

        # Direct file path (demo / tmp/coremark-style): results_csv or suite-specific keys
        if files.get("results_speccpu_intrate_csv"):
            p = Path(files["results_speccpu_intrate_csv"])
            if p.exists():
                intrate_csv = p
        if files.get("results_speccpu_fprate_csv"):
            p = Path(files["results_speccpu_fprate_csv"])
            if p.exists():
                fprate_csv = p
        if files.get("results_csv") and not (intrate_csv or fprate_csv):
            p = Path(files["results_csv"])
            if p.exists():
                name_lower = p.name.lower()
                if "fprate" in name_lower or "fpspeed" in name_lower:
                    fprate_csv = p
                else:
                    intrate_csv = p

        # When using files, result_dir for version/status can be CSV parent if no extracted_path
        if result_dir == Path(".") and (intrate_csv or fprate_csv):
            result_dir = (intrate_csv or fprate_csv).parent

        if not (intrate_csv or fprate_csv or intspeed_csv or fpspeed_csv):
            # From extracted_path: CSVs in result_dir directly or in result/
            result_subdir = result_dir / "result"
            if not result_subdir.exists():
                result_subdir = result_dir
            for csv_file in result_subdir.glob("*.csv"):
                name_lower = csv_file.name.lower()
                if "intrate" in name_lower or "intspeed" in name_lower:
                    if "rate" in name_lower:
                        intrate_csv = csv_file
                    elif "speed" in name_lower:
                        intspeed_csv = csv_file
                elif "fprate" in name_lower or "fpspeed" in name_lower:
                    if "rate" in name_lower:
                        fprate_csv = csv_file
                    elif "speed" in name_lower:
                        fpspeed_csv = csv_file

        # Parse version (from result_dir when available)
        version_file = result_dir / "version"
        version = parse_version_file(version_file) if version_file.exists() else None

        # Parse test status
        status_file = result_dir / "test_results_report"
        status = "PASS" if status_file.exists() and "Ran" in read_file_content(status_file) else "UNKNOWN"

        runs = {}
        run_num = 0

        # Parse integer suite (prefer rate over speed)
        int_csv = intrate_csv or intspeed_csv
        int_suite_name = "intrate" if intrate_csv else "intspeed"

        if int_csv and int_csv.exists():
            logger.info(f"Parsing integer suite from: {int_csv.name}")
            int_data = self._parse_suite_csv(int_csv, int_suite_name)
            if int_data:
                runs[create_run_key(run_num)] = self._build_run_object(
                    run_number=run_num,
                    suite_data=int_data,
                    suite_name=int_suite_name,
                    status=status,
                    version=version
                )
                run_num += 1
        else:
            logger.warning("No integer suite CSV file found (intrate/intspeed)")

        # Parse floating point suite (prefer rate over speed)
        fp_csv = fprate_csv or fpspeed_csv
        fp_suite_name = "fprate" if fprate_csv else "fpspeed"

        if fp_csv and fp_csv.exists():
            logger.info(f"Parsing floating point suite from: {fp_csv.name}")
            fp_data = self._parse_suite_csv(fp_csv, fp_suite_name)
            if fp_data:
                runs[create_run_key(run_num)] = self._build_run_object(
                    run_number=run_num,
                    suite_data=fp_data,
                    suite_name=fp_suite_name,
                    status=status,
                    version=version
                )
                run_num += 1
        else:
            logger.warning("No floating point suite CSV file found (fprate/fpspeed)")

        if runs:
            logger.info(f"Parsed {len(runs)} SPEC CPU 2017 suite(s)")
        else:
            logger.warning("No SPEC CPU 2017 suite data found")

        return runs

    def _parse_suite_csv(self, csv_path: Path, suite_name: str) -> Dict[str, Any]:
        """
        Parse a SPEC CPU 2017 suite CSV file.

        Supports two formats:
        1. Timestamped: "Benchmarks,Base copies,Base Run Time,Base Rate,Start_Date,End_Date"
           - Required. Timestamps must be valid ISO 8601 (e.g. 2026-02-26T03:21:32Z).
        2. Legacy: "Benchmark,Base # Copies,Est. Base Run Time,Est. Base Rate" (no timestamps)
           - Not supported; raises ProcessorError.

        Returns dict with suite-level and per-benchmark data, plus start_timestamp,
        end_timestamp, and timeseries when format has Start_Date/End_Date.
        """
        content = read_file_content(csv_path)
        lines = content.splitlines()

        # Find first non-comment, non-empty line that looks like a header
        header_line_idx: Optional[int] = None
        header_has_timestamps = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "Benchmark" in stripped and "," in stripped:
                header_line_idx = i
                header_has_timestamps = "Start_Date" in stripped and "End_Date" in stripped
                break

        if header_line_idx is None:
            raise ProcessorError(
                "SPEC CPU 2017 results require a CSV header with benchmark and timestamp columns. "
                f"No recognized header line found in {csv_path.name}. "
                "Expected: 'Benchmarks,Base copies,Base Run Time,Base Rate,Start_Date,End_Date'."
            )

        if header_has_timestamps:
            return self._parse_suite_csv_timestamped(csv_path, suite_name, lines, header_line_idx)

        # Legacy format (Benchmark, Base # Copies, ...) without Start_Date/End_Date
        raise ProcessorError(
            "SPEC CPU 2017 results require timestamps. The CSV must include Start_Date and End_Date "
            "columns (ISO 8601, e.g. 2026-02-26T03:21:32Z). This file appears to use the legacy format "
            "without timestamps."
        )

    def _parse_suite_csv_timestamped(
        self, csv_path: Path, suite_name: str, lines: List[str], header_row: int
    ) -> Dict[str, Any]:
        """Parse CSV with Benchmarks,...,Start_Date,End_Date. Requires valid timestamps."""
        benchmarks = {}
        rates: List[float] = []
        timeseries_data: List[Tuple[str, Dict[str, Any]]] = []
        all_starts: List[str] = []
        all_ends: List[str] = []

        reader = csv.DictReader(io.StringIO("\n".join(lines[header_row:])))

        for row in reader:
            # Column names may be "Benchmarks" or "Benchmark"
            bench_key = "Benchmarks" if "Benchmarks" in row else "Benchmark"
            benchmark_name = (row.get(bench_key) or "").strip()
            if not benchmark_name or benchmark_name.startswith("#"):
                continue

            start_ts = (row.get("Start_Date") or "").strip()
            end_ts = (row.get("End_Date") or "").strip()

            start_ts = _validate_iso8601_timestamp(start_ts, f"Row for benchmark {benchmark_name!r}:")
            end_ts = _validate_iso8601_timestamp(end_ts, f"Row for benchmark {benchmark_name!r}:")

            all_starts.append(start_ts)
            all_ends.append(end_ts)

            base_copies = None
            base_run_time = None
            base_rate = None
            for key, val in row.items():
                if key in (bench_key, "Start_Date", "End_Date"):
                    continue
                try:
                    if "copies" in key.lower():
                        base_copies = int(float(val))
                    elif "run time" in key.lower() or "runtime" in key.lower():
                        base_run_time = float(val)
                    elif "rate" in key.lower():
                        base_rate = float(val)
                        rates.append(base_rate)
                except (ValueError, TypeError):
                    pass

            benchmark_data = {"benchmark": benchmark_name}
            if base_copies is not None:
                benchmark_data["copies"] = base_copies
            if base_run_time is not None:
                benchmark_data["base_runtime"] = base_run_time
            if base_rate is not None:
                benchmark_data["base_rate"] = base_rate

            if benchmark_data.get("base_rate") is not None:
                benchmarks[benchmark_name] = benchmark_data
                metrics = {k: v for k, v in benchmark_data.items() if k != "benchmark" and isinstance(v, (int, float))}
                timeseries_data.append((start_ts, metrics))

        if not benchmarks:
            raise ProcessorError(
                f"SPEC CPU 2017 CSV {csv_path.name}: no valid benchmark rows with Start_Date/End_Date. "
                "Expected format: Benchmarks,Base copies,Base Run Time,Base Rate,Start_Date,End_Date."
            )

        from functools import reduce
        import operator

        product = reduce(operator.mul, rates, 1)
        base_score = product ** (1.0 / len(rates)) if rates else None

        suite_data: Dict[str, Any] = {
            "benchmarks": benchmarks,
            "num_benchmarks": len(benchmarks),
            "rates": rates,
            "start_timestamp": min(all_starts),
            "end_timestamp": max(all_ends),
            "timeseries_data": timeseries_data,
        }
        if base_score is not None:
            suite_data["base_score"] = base_score
            suite_data["est_spec_score"] = base_score

        return suite_data

    def _build_run_object(
        self,
        run_number: int,
        suite_data: Dict[str, Any],
        suite_name: str,
        status: str,
        version: Optional[str]
    ) -> Run:
        """Build a Run object for a SPEC CPU suite. Uses timestamps from suite_data when present."""

        # Build suite-level metrics
        metrics = {
            "suite_name": suite_name,
            "num_benchmarks": suite_data.get("num_benchmarks", 0),
        }

        if "base_score" in suite_data:
            metrics["base_score"] = suite_data["base_score"]

        if "est_spec_score" in suite_data:
            metrics["est_spec_score"] = suite_data["est_spec_score"]

        # Add per-benchmark metrics
        benchmarks_dict = {}
        for bench_name, bench_data in suite_data.get("benchmarks", {}).items():
            bench_metrics = {}
            for key in ["base_score", "base_runtime", "base_rate", "copies", "threads"]:
                if key in bench_data:
                    bench_metrics[key] = bench_data[key]
            benchmarks_dict[bench_name] = bench_metrics

        if benchmarks_dict:
            metrics["benchmarks"] = benchmarks_dict

        # Build configuration
        configuration = {
            "suite": suite_name,
            "num_benchmarks": suite_data.get("num_benchmarks", 0),
        }
        if version:
            configuration["version"] = version
        first_bench = next(iter(suite_data.get("benchmarks", {}).values()), {})
        if "copies" in first_bench:
            configuration["copies"] = first_bench["copies"]

        # Timestamps and timeseries from CSV
        start_time = suite_data.get("start_timestamp")
        end_time = suite_data.get("end_timestamp")
        duration_seconds = None
        if start_time and end_time:
            try:
                from datetime import datetime
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                duration_seconds = (end_dt - start_dt).total_seconds()
            except (ValueError, TypeError):
                pass

        timeseries: Optional[Dict[str, TimeSeriesPoint]] = None
        ts_data = suite_data.get("timeseries_data") or []
        if ts_data:
            timeseries = {}
            for seq, (ts, point_metrics) in enumerate(ts_data):
                timeseries[create_sequence_key(seq)] = TimeSeriesPoint(
                    timestamp=ts,
                    metrics=point_metrics,
                )
        elif start_time:
            # Single point at run start with suite metrics
            timeseries = {
                create_sequence_key(0): TimeSeriesPoint(
                    timestamp=start_time,
                    metrics={k: v for k, v in metrics.items() if isinstance(v, (int, float))},
                )
            }

        return Run(
            run_number=run_number,
            status=status,
            metrics=metrics,
            configuration=configuration,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration_seconds,
            timeseries=timeseries,
        )

    def build_results(self) -> Any:
        """
        Build Results object with overall primary metric.

        Override to set the document's primary metric to the best/combined suite score.
        """
        results = super().build_results()

        # Calculate overall SPEC score from both suites
        if results and results.runs:
            suite_scores = []

            for run_key, run in results.runs.items():
                if run.metrics and 'base_score' in run.metrics:
                    suite_scores.append(run.metrics['base_score'])

            if suite_scores:
                # Use geometric mean of suite scores as overall SPEC score
                from functools import reduce
                import operator
                product = reduce(operator.mul, suite_scores, 1)
                overall_score = product ** (1.0 / len(suite_scores))

                results.primary_metric = PrimaryMetric(
                    name='spec_score',
                    value=overall_score,
                    unit='score'
                )

        return results
