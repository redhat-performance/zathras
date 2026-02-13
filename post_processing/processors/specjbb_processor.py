"""
SpecJBB (SPECjbb2005) Java Benchmark Processor

Processes SpecJBB results including:
- Multiple warehouse configurations (2, 4, 6, 8, 10, 12, 14, 16)
- Throughput (Bops - Business Operations per Second) for each
- Overall benchmark score
- Peak throughput identification

Expects CSV with Start_Date and End_Date columns (ISO 8601). Legacy
colon-delimited format without timestamps is not supported.
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
import logging

from .base_processor import BaseProcessor, ProcessorError
from ..schema import Run, TimeSeriesPoint, create_run_key, create_sequence_key

logger = logging.getLogger(__name__)

# ISO 8601 pattern (e.g. 2026-02-04T17:07:07Z or with fractional seconds)
_ISO8601_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
)


def _validate_iso8601_timestamp(value: str, context: str) -> str:
    """Validate and return an ISO 8601 timestamp string. Raises ProcessorError if invalid."""
    if not value or not isinstance(value, str):
        raise ProcessorError(
            f"SpecJBB results require timestamps. {context} "
            "Start_Date and End_Date must be non-empty strings."
        )
    value = value.strip()
    if not value:
        raise ProcessorError(
            f"SpecJBB results require timestamps. {context} "
            "Start_Date and End_Date cannot be blank."
        )
    if not _ISO8601_PATTERN.match(value):
        raise ProcessorError(
            f"SpecJBB results require valid ISO 8601 timestamps. {context} "
            f"Got: {value!r}. Expected format: YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DDTHH:MM:SS.ffffffZ"
        )
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise ProcessorError(
            f"SpecJBB results require valid ISO 8601 timestamps. {context} "
            f"Cannot parse {value!r}: {e}"
        ) from e
    return value


class SpecJBBProcessor(BaseProcessor):
    """Processor for SpecJBB Java benchmark results."""

    def get_test_name(self) -> str:
        return "specjbb"

    def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse SpecJBB runs into object-based structure.

        Resolves CSV path via extracted_result["files"] (e.g. results_specjbb_csv)
        when provided, otherwise from extracted_path (direct or specjbb_* subdir).
        Requires CSV to include Start_Date and End_Date columns (ISO 8601).
        Raises ProcessorError if timestamps are missing or malformed.

        Returns:
            {
                "run_1": {
                    "run_number": 1,
                    "status": "PASS",
                    "metrics": {...},
                    "timeseries": {
                        "sequence_0": {"timestamp": "...", "metrics": {...}},
                        ...
                    }
                }
            }
        """
        csv_file: Optional[Path] = None
        result_dir: Optional[Path] = None

        files = extracted_result.get("files") or {}
        if files.get("results_specjbb_csv"):
            csv_file = Path(files["results_specjbb_csv"])
            result_dir = csv_file.parent
        else:
            extracted_path = extracted_result.get("extracted_path")
            if not extracted_path:
                logger.warning(
                    "SpecJBB results require either extracted_result['files']['results_specjbb_csv'] "
                    "or extracted_result['extracted_path']."
                )
                return {}
            result_dir = Path(extracted_path)
            direct_csv = result_dir / "results_specjbb.csv"
            if direct_csv.exists():
                csv_file = direct_csv
            else:
                csv_file = self._find_csv_file(result_dir)

        if not csv_file or not csv_file.exists():
            logger.warning(f"SpecJBB CSV file not found: {csv_file}")
            return {}

        warehouse_data, num_jvms = self._parse_csv(csv_file)

        # Parse detailed results from .txt file for overall score (optional)
        txt_file = None
        if result_dir:
            txt_file = self._find_txt_file(result_dir)
        overall_score = None
        if txt_file:
            overall_score = self._extract_overall_score(txt_file)
        if num_jvms is None:
            num_jvms = self._extract_num_jvms(csv_file)

        runs = {}
        if warehouse_data:
            run_key = create_run_key(0)
            runs[run_key] = self._build_run_object(
                run_number=0,
                warehouse_data=warehouse_data,
                overall_score=overall_score,
                num_jvms=num_jvms or 1,
            )

        logger.info(f"Parsed {len(runs)} SpecJBB runs")
        return runs

    def _find_csv_file(self, specjbb_dir: Path) -> Optional[Path]:
        """Find the CSV file in the SpecJBB results directory."""
        # Look for results_specjbb.csv
        csv_files = list(specjbb_dir.rglob("results_specjbb.csv"))
        if csv_files:
            return csv_files[0]

        # Fallback: any CSV file
        csv_files = list(specjbb_dir.rglob("*.csv"))
        if csv_files:
            return csv_files[0]

        return None

    def _find_txt_file(self, specjbb_dir: Path) -> Optional[Path]:
        """Find the detailed results .txt file."""
        txt_files = list(specjbb_dir.rglob("SPECjbb*.txt"))
        if txt_files:
            return txt_files[0]
        return None

    def _parse_csv(self, csv_file: Path) -> Tuple[List[Dict[str, Any]], Optional[int]]:
        """
        Parse SpecJBB CSV file.

        Supported format (required): comma-delimited with header
        Warehouses,Bops,Numb_JVMs,Start_Date,End_Date and ISO 8601 timestamps.
        Legacy format (Warehouses:Bops without timestamps) is not supported;
        raises ProcessorError with a clear message.

        Returns:
            (warehouse_data, num_jvms). Each warehouse_data item has
            warehouses, throughput_bops, start_timestamp, end_timestamp.
            num_jvms from first data row or None.
        """
        warehouse_data: List[Dict[str, Any]] = []
        num_jvms: Optional[int] = None
        header_seen = False
        has_timestamp_columns = False

        try:
            with open(csv_file, "r") as f:
                lines = f.readlines()
        except OSError as e:
            raise ProcessorError(f"SpecJBB: cannot read CSV file {csv_file}: {e}") from e

        for line in lines:
            line_stripped = line.strip()

            if not line_stripped:
                continue

            if line_stripped.startswith("#"):
                continue

            # Expect header: Warehouses,Bops,Numb_JVMs,Start_Date,End_Date
            if not header_seen:
                if "," in line_stripped:
                    tokens = [t.strip() for t in line_stripped.split(",")]
                    if (
                        len(tokens) >= 5
                        and tokens[0] == "Warehouses"
                        and tokens[1] == "Bops"
                        and tokens[2] == "Numb_JVMs"
                        and tokens[3] == "Start_Date"
                        and tokens[4] == "End_Date"
                    ):
                        header_seen = True
                        has_timestamp_columns = True
                        continue
                    raise ProcessorError(
                        "SpecJBB results require timestamps. The CSV header must be "
                        "Warehouses,Bops,Numb_JVMs,Start_Date,End_Date (comma-delimited). "
                        f"Got: {line_stripped[:80]!r}."
                    )
                if line_stripped == "Warehouses:Bops" or (
                    ":" in line_stripped and line_stripped.split(":")[0].strip() == "Warehouses"
                ):
                    raise ProcessorError(
                        "SpecJBB results require timestamps. The CSV must use comma-delimited "
                        "format with Start_Date and End_Date columns. "
                        "Legacy colon-delimited format (Warehouses:Bops) without timestamps is not supported."
                    )
                continue

            if not has_timestamp_columns:
                continue

            parts = [p.strip() for p in line_stripped.split(",")]
            if len(parts) < 5:
                raise ProcessorError(
                    f"SpecJBB CSV row must have at least 5 columns (Warehouses,Bops,Numb_JVMs,Start_Date,End_Date). "
                    f"Got {len(parts)}: {line_stripped[:80]!r}."
                )
            try:
                warehouses = int(parts[0])
                throughput_bops = int(parts[1])
                n_jvms = int(parts[2])
                if num_jvms is None:
                    num_jvms = n_jvms
            except ValueError as e:
                raise ProcessorError(
                    f"SpecJBB CSV: invalid numeric value in row (Warehouses,Bops,Numb_JVMs). "
                    f"Row: {line_stripped[:80]!r}. {e}"
                ) from e

            start_ts = _validate_iso8601_timestamp(
                parts[3], f"Row Warehouses={warehouses}:"
            )
            end_ts = _validate_iso8601_timestamp(
                parts[4], f"Row Warehouses={warehouses}:"
            )

            warehouse_data.append({
                "warehouses": warehouses,
                "throughput_bops": throughput_bops,
                "start_timestamp": start_ts,
                "end_timestamp": end_ts,
            })
        if not has_timestamp_columns and not warehouse_data:
            raise ProcessorError(
                "SpecJBB results require timestamps. No header line with "
                "Warehouses,Bops,Numb_JVMs,Start_Date,End_Date was found."
            )
        return warehouse_data, num_jvms

    def _extract_overall_score(self, txt_file: Path) -> Optional[int]:
        """
        Extract overall SpecJBB score from .txt file.

        Looks for lines like:
        SPECjbb2005 bops = 293941, SPECjbb2005 bops/JVM = 293941
        or
        Throughput      293941
        """
        try:
            with open(txt_file, 'r') as f:
                content = f.read()

                # Try pattern 1: SPECjbb2005 bops = <score>
                match = re.search(r'SPECjbb\d+\s+bops\s*=\s*(\d+)', content)
                if match:
                    return int(match.group(1))

                # Try pattern 2: Throughput      <score>
                match = re.search(r'Throughput\s+(\d+)', content)
                if match:
                    return int(match.group(1))

        except Exception as e:
            logger.warning(f"Failed to extract overall score from {txt_file}: {e}")

        return None

    def _extract_num_jvms(self, csv_file: Path) -> int:
        """Extract number of JVMs from CSV header comments."""
        try:
            with open(csv_file, 'r') as f:
                for line in f:
                    if 'Number of jvms:' in line:
                        match = re.search(r'Number of jvms:\s*(\d+)', line)
                        if match:
                            return int(match.group(1))
        except Exception as e:
            logger.warning(f"Failed to extract num JVMs: {e}")

        return 1  # Default

    def _build_run_object(
        self,
        run_number: int,
        warehouse_data: List[Dict[str, Any]],
        overall_score: Optional[int],
        num_jvms: int
    ) -> Run:
        """Convert raw warehouse data to Run dataclass object."""

        # Calculate metrics from warehouse data
        metrics = {}
        peak_warehouses = None
        peak_throughput = None

        if warehouse_data:
            # Find peak throughput
            peak_data = max(warehouse_data, key=lambda x: x['throughput_bops'])
            peak_warehouses = peak_data['warehouses']
            peak_throughput = peak_data['throughput_bops']

            # Store aggregate metrics
            metrics['peak_warehouse_config'] = peak_warehouses
            metrics['peak_throughput_bops'] = peak_throughput

            if overall_score:
                metrics['overall_score_bops'] = overall_score

            # Store throughput for each warehouse configuration
            for data in warehouse_data:
                warehouses = data['warehouses']
                throughput = data['throughput_bops']
                metrics[f'throughput_warehouses_{warehouses}_bops'] = throughput

        # Build time series from warehouse configurations using timestamps from CSV
        timeseries = {}
        for idx, data in enumerate(warehouse_data):
            ts = data.get("start_timestamp")
            if not ts:
                raise ProcessorError(
                    f"SpecJBB run {run_number} sequence {idx} (warehouses={data.get('warehouses')}) "
                    "is missing start_timestamp from the CSV."
                )
            _validate_iso8601_timestamp(ts, f"Run {run_number}, sequence {idx}:")
            seq_key = create_sequence_key(idx)
            timeseries[seq_key] = TimeSeriesPoint(
                timestamp=ts,
                metrics={
                    "warehouses": data["warehouses"],
                    "throughput_bops": data["throughput_bops"],
                },
            )

        # Build configuration
        config = {
            'num_jvms': num_jvms,
            'warehouse_configurations': [d['warehouses'] for d in warehouse_data]
        }

        return Run(
            run_number=run_number,
            status="PASS",  # SpecJBB doesn't provide explicit pass/fail
            metrics=metrics,
            configuration=config,
            timeseries=timeseries if timeseries else None
        )
