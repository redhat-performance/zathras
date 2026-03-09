"""
Auto HPL (High-Performance Linpack) Processor

Processes HPL benchmark results for measuring floating-point computing power.

Auto HPL produces:
- hpl-*.csv - Performance results (matrix size, block size, process grid, time, Gflops)
  CSV must include Start_Date and End_Date (ISO 8601) for run timestamps.
- auto_hpl.out - Detailed execution log
- test_results_report - PASS/FAIL status
- version - Test wrapper version
"""

import re
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import logging

from .base_processor import BaseProcessor, ProcessorError
from ..schema import Run, TimeSeriesPoint, create_run_key, create_sequence_key
from ..utils.parser_utils import (
    parse_version_file,
    read_file_content
)

logger = logging.getLogger(__name__)

# ISO 8601 pattern (e.g. 2026-02-04T00:12:03Z or with fractional seconds)
_ISO8601_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
)


def _validate_iso8601_timestamp(value: str, context: str) -> str:
    """Validate and return an ISO 8601 timestamp string. Raises ProcessorError if invalid."""
    if not value or not isinstance(value, str):
        raise ProcessorError(
            f"Auto HPL results require timestamps. {context} "
            "Start_Date and End_Date must be non-empty strings."
        )
    value = value.strip()
    if not value:
        raise ProcessorError(
            f"Auto HPL results require timestamps. {context} "
            "Start_Date and End_Date cannot be blank."
        )
    if not _ISO8601_PATTERN.match(value):
        raise ProcessorError(
            f"Auto HPL results require valid ISO 8601 timestamps. {context} "
            f"Got: {value!r}. Expected format: YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DDTHH:MM:SS.ffffffZ"
        )
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise ProcessorError(
            f"Auto HPL results require valid ISO 8601 timestamps. {context} "
            f"Cannot parse {value!r}: {e}"
        ) from e
    return value


class AutoHPLProcessor(BaseProcessor):
    """Processor for Auto HPL (High-Performance Linpack) benchmark results"""

    def get_test_name(self) -> str:
        return "auto_hpl"

    def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Auto HPL runs into object-based structure

        Single run with HPL performance metrics. Timestamps are taken from the
        CSV Start_Date/End_Date columns (required). Raises ProcessorError if
        timestamps are missing or malformed.

        Returns:
            {
                "run_0": {
                    "run_number": 0,
                    "status": "PASS",
                    "start_time": "2026-02-04T00:12:03Z",
                    "end_time": "2026-02-04T00:12:33Z",
                    "metrics": {...},
                    "configuration": {...},
                    "timeseries": {"sequence_0": TimeSeriesPoint(...)}
                }
            }
        """
        csv_file: Optional[Path] = None
        result_dir: Optional[Path] = None

        files = extracted_result.get("files") or {}
        if files.get("results_csv") or files.get("results_auto_hpl_csv"):
            path_str = files.get("results_auto_hpl_csv") or files.get("results_csv")
            csv_file = Path(path_str)
            result_dir = csv_file.parent
        else:
            result_dir = extracted_result.get("extracted_path")
            if not result_dir:
                raise ProcessorError(
                    "Auto HPL results require either 'files' with results_csv or results_auto_hpl_csv, "
                    "or 'extracted_path' to a directory containing results_auto_hpl.csv or hpl-*.csv."
                )
            result_dir = Path(result_dir)
            # CSV directly in result dir (e.g. tmp/autohpl/results_auto_hpl.csv) or hpl-*.csv
            direct = result_dir / "results_auto_hpl.csv"
            if direct.exists():
                csv_file = direct
            else:
                csv_files = list(result_dir.glob("hpl-*.csv"))
                if not csv_files:
                    raise ProcessorError(
                        f"Auto HPL results not found: no results_auto_hpl.csv or hpl-*.csv in {result_dir}. "
                        "Provide a CSV with Start_Date and End_Date columns (ISO 8601)."
                    )
                csv_file = csv_files[0]

        if not csv_file or not csv_file.exists():
            raise ProcessorError(
                f"Auto HPL CSV file not found: {csv_file}. "
                "Ensure the results CSV exists and includes Start_Date and End_Date (ISO 8601)."
            )

        hpl_result = self._parse_hpl_csv(csv_file)
        if not hpl_result:
            raise ProcessorError(
                f"No valid HPL data in {csv_file}. CSV must have header "
                "T/V,N,NB,P,Q,Time,Gflops,Start_Date,End_Date and a data row with valid timestamps."
            )

        if result_dir:
            version_file = result_dir / "version"
            version = parse_version_file(version_file) if version_file.exists() else None
            status_file = result_dir / "test_results_report"
            status = "PASS" if status_file.exists() and "Ran" in read_file_content(status_file) else "UNKNOWN"
        else:
            version = None
            status = "UNKNOWN"

        run_data = self._build_run_object(
            run_number=0,
            hpl_result=hpl_result,
            status=status,
            version=version
        )
        runs = {create_run_key(0): run_data}

        logger.info(f"Parsed 1 Auto HPL run: {hpl_result.get('gflops', 0):.2f} GFLOPS")
        return runs

    def _parse_hpl_csv(self, csv_file: Path) -> Dict[str, Any]:
        """
        Parse HPL CSV file. Requires comma-delimited format with Start_Date and End_Date.

        Supported format (comma-delimited):
        T/V,N,NB,P,Q,Time,Gflops,Start_Date,End_Date
        WR12R2R4,273408,384,4,8,1639.91,8.3086e+03,2026-02-04T00:12:03Z,2026-02-04T00:12:33Z

        Raises ProcessorError if timestamps are missing or malformed. Legacy
        colon-delimited format without timestamps is not supported.
        """
        hpl_result = {}
        header_has_timestamps = False
        header_cols: Optional[list] = None

        with open(csv_file, 'r') as f:
            for line in f:
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                if line_stripped.startswith('#'):
                    continue

                # Comma-delimited header with Start_Date, End_Date
                if line_stripped.startswith("T/V") and "," in line_stripped:
                    tokens = [t.strip() for t in line_stripped.split(",")]
                    if len(tokens) >= 9 and tokens[-2] == "Start_Date" and tokens[-1] == "End_Date":
                        header_has_timestamps = True
                        header_cols = tokens
                        continue
                    raise ProcessorError(
                        "Auto HPL results require timestamps. The CSV header must be comma-delimited "
                        "and include Start_Date and End_Date as the last two columns "
                        "(e.g. T/V,N,NB,P,Q,Time,Gflops,Start_Date,End_Date)."
                    )

                # Legacy colon-delimited line (no timestamps)
                if ":" in line_stripped and "," not in line_stripped:
                    raise ProcessorError(
                        "Auto HPL results require timestamps. The CSV must be comma-delimited "
                        "with Start_Date and End_Date columns. Colon-delimited format without "
                        "timestamps is not supported."
                    )

                # Data row (comma-delimited)
                if header_has_timestamps and header_cols:
                    parts = [p.strip() for p in line_stripped.split(",")]
                    if len(parts) < 9:
                        raise ProcessorError(
                            f"Auto HPL CSV data row has too few columns (expected at least 9 including "
                            f"Start_Date and End_Date, got {len(parts)})."
                        )
                    try:
                        variant = parts[0]
                        n = int(parts[1])
                        nb = int(parts[2])
                        p = int(parts[3])
                        q = int(parts[4])
                        time_sec = float(parts[5])
                        gflops = float(parts[6])
                        start_ts = parts[-2]
                        end_ts = parts[-1]
                    except (ValueError, IndexError) as e:
                        raise ProcessorError(
                            f"Auto HPL CSV: invalid numeric or column in data row: {e}"
                        ) from e

                    start_timestamp = _validate_iso8601_timestamp(start_ts, "Start_Date:")
                    end_timestamp = _validate_iso8601_timestamp(end_ts, "End_Date:")

                    hpl_result = {
                        'variant': variant,
                        'matrix_size': n,
                        'block_size': nb,
                        'process_grid_p': p,
                        'process_grid_q': q,
                        'time_seconds': time_sec,
                        'gflops': gflops,
                        'start_timestamp': start_timestamp,
                        'end_timestamp': end_timestamp,
                    }
                    break

        if not header_has_timestamps and not hpl_result:
            with open(csv_file, 'r') as f:
                for line in f:
                    if line.strip().startswith('#'):
                        continue
                    if 'T/V' in line and ':' in line and ',' not in line.strip():
                        raise ProcessorError(
                            "Auto HPL results require timestamps. The CSV must be comma-delimited "
                            "with Start_Date and End_Date columns. Legacy colon-delimited format "
                            "is not supported."
                        )
                    break
        if not header_has_timestamps and not hpl_result:
            raise ProcessorError(
                "Auto HPL results require timestamps. No header line with "
                "T/V,N,NB,P,Q,Time,Gflops,Start_Date,End_Date was found."
            )

        return hpl_result

    def _build_run_object(
        self,
        run_number: int,
        hpl_result: Dict[str, Any],
        status: str,
        version: str
    ) -> Run:
        """Build a Run object from HPL data. Uses start_timestamp/end_timestamp from CSV."""

        start_ts = hpl_result.get("start_timestamp")
        end_ts = hpl_result.get("end_timestamp")
        if not start_ts or not end_ts:
            raise ProcessorError(
                "Auto HPL results require timestamps. Run is missing Start_Date or End_Date from the CSV."
            )

        metrics = {
            'gflops': hpl_result.get('gflops', 0),
            'time_seconds': hpl_result.get('time_seconds', 0),
            'matrix_size': hpl_result.get('matrix_size', 0),
            'block_size': hpl_result.get('block_size', 0),
            'process_grid_p': hpl_result.get('process_grid_p', 0),
            'process_grid_q': hpl_result.get('process_grid_q', 0),
            'total_processes': hpl_result.get('process_grid_p', 0) * hpl_result.get('process_grid_q', 0)
        }

        configuration = {
            'variant': hpl_result.get('variant', 'unknown'),
            'matrix_size_n': hpl_result.get('matrix_size', 0),
            'block_size_nb': hpl_result.get('block_size', 0),
            'process_grid': f"{hpl_result.get('process_grid_p', 0)}x{hpl_result.get('process_grid_q', 0)}"
        }
        if version:
            configuration['version'] = version

        timeseries = {
            create_sequence_key(0): TimeSeriesPoint(
                timestamp=start_ts,
                metrics=metrics.copy(),
            )
        }

        return Run(
            run_number=run_number,
            status=status,
            start_time=start_ts,
            end_time=end_ts,
            duration_seconds=hpl_result.get('time_seconds'),
            metrics=metrics,
            configuration=configuration,
            timeseries=timeseries,
            timeseries_summary=None
        )
