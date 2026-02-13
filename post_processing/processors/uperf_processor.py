"""
Uperf processor for Zathras results.

Uperf is a network performance tool that measures throughput, latency, and transaction rate
across various protocols, packet sizes, and concurrency levels.

Timestamps are taken from the benchmark output (CSV Start_Date/End_Date). When only
run-level start/end exist (e.g. run_metadata in net_results), timestamps are interpolated
for each data point. Missing or malformed timestamps raise ProcessorError.
"""

import re
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from pathlib import Path
import logging
import statistics

from .base_processor import BaseProcessor, ProcessorError
from ..schema import Run, TimeSeriesPoint, TimeSeriesSummary, create_run_key, create_sequence_key
from ..utils.parser_utils import read_file_content

logger = logging.getLogger(__name__)

# ISO 8601 pattern (e.g. 2026-02-10T14:41:49Z or with fractional seconds)
_ISO8601_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
)


def _validate_iso8601_timestamp(value: str, context: str) -> str:
    """Validate and return an ISO 8601 timestamp string. Raises ProcessorError if invalid."""
    if not value or not isinstance(value, str):
        raise ProcessorError(
            f"Uperf results require timestamps. {context} "
            "Start_Date and End_Date must be non-empty strings."
        )
    value = value.strip()
    if not value:
        raise ProcessorError(
            f"Uperf results require timestamps. {context} "
            "Start_Date and End_Date cannot be blank."
        )
    if not _ISO8601_PATTERN.match(value):
        raise ProcessorError(
            f"Uperf results require valid ISO 8601 timestamps. {context} "
            f"Got: {value!r}. Expected format: YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DDTHH:MM:SS.ffffffZ"
        )
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise ProcessorError(
            f"Uperf results require valid ISO 8601 timestamps. {context} "
            f"Cannot parse {value!r}: {e}"
        ) from e
    return value


class UperfProcessor(BaseProcessor):
    """Processor for Uperf network performance benchmark results."""

    def get_test_name(self) -> str:
        return "uperf"

    def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Run]:
        """
        Parse Uperf runs into object-based structure.

        Supports:
        - Direct results path via extracted_result['files']['results_uperf_csv'] (single CSV
          with Start_Date/End_Date; demos can pass a file path).
        - extracted_path: look for results_uperf.csv directly in that directory, or in a
          uperf_* subdir; if not found, use net_results/ with run_metadata timestamps.

        Uperf runs multiple test configurations; we treat as one run with timeseries
        points per (configuration, instance_count). Timestamps come from the CSV or
        from run-level Start_Date/End_Date with interpolation.

        Returns:
            A dictionary of Run objects, keyed by run_key (typically "run_0").
        """
        csv_file: Optional[Path] = None
        result_dir: Optional[Path] = None

        files = extracted_result.get("files") or {}
        if files.get("results_uperf_csv"):
            csv_file = Path(files["results_uperf_csv"])
            if not csv_file.exists():
                raise ProcessorError(
                    f"Uperf results file not found: {csv_file}. "
                    "Ensure results_uperf_csv path is valid."
                )
            result_dir = csv_file.parent
        else:
            extracted_path = Path(extracted_result["extracted_path"])
            # CSV in result dir directly (e.g. tmp/uperf/results_uperf.csv) or in uperf_*
            direct_csv = extracted_path / "results_uperf.csv"
            if direct_csv.exists():
                csv_file = direct_csv
                result_dir = extracted_path
            else:
                uperf_dirs = list(extracted_path.glob("uperf_*"))
                if uperf_dirs:
                    candidate = uperf_dirs[0] / "results_uperf.csv"
                    if candidate.exists():
                        csv_file = candidate
                        result_dir = uperf_dirs[0]
                if not csv_file:
                    # Fall back to net_results directory layout (requires run_metadata timestamps)
                    net_results_dirs = list(extracted_path.rglob("net_results"))
                    if not net_results_dirs:
                        raise ProcessorError(
                            f"Uperf: no results_uperf.csv in {extracted_path} and no net_results directory found. "
                            "Provide results_uperf.csv with Start_Date/End_Date columns or net_results with run_metadata."
                        )
                    net_results_dir = net_results_dirs[0]
                    run_data = self._parse_uperf_net_results(net_results_dir)
                    run_objects = {}
                    if run_data:
                        run_objects[create_run_key(0)] = self._build_run_object(run_data)
                    logger.info(
                        f"Parsed Uperf: 1 run with {len(run_data.get('configurations', {}))} configurations"
                    )
                    return run_objects

        if csv_file and csv_file.exists():
            run_data = self._parse_uperf_single_csv(csv_file)
            run_objects = {}
            if run_data:
                run_objects[create_run_key(0)] = self._build_run_object(run_data)
            logger.info(
                f"Parsed Uperf: 1 run with {len(run_data.get('timeseries', {}))} timeseries points"
            )
            return run_objects

        raise ProcessorError(
            "Uperf: no results_uperf.csv found and no net_results with run_metadata. "
            "Expected CSV with columns including Start_Date,End_Date (ISO 8601)."
        )

    def _parse_uperf_single_csv(self, csv_file: Path) -> Dict[str, Any]:
        """
        Parse a single Uperf results CSV with Start_Date/End_Date.

        Expected format (comma-delimited):
          number_procs,Gb_Sec,trans_sec,lat_usec,test_type,packet_type,packet_size,Start_Date,End_Date
        Comment lines (#) are skipped. Raises ProcessorError if timestamps are missing or malformed.
        """
        run_data = {
            "run_number": 0,
            "status": "PASS",
            "configurations": {},
            "timeseries": {},
            "overall_metrics": {},
        }
        content = read_file_content(csv_file)
        lines = content.strip().split("\n")

        start_idx: Optional[int] = None
        end_idx: Optional[int] = None
        header_cols: List[str] = []
        sequence = 0
        all_throughput_values: List[float] = []

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith("#"):
                continue

            parts = [p.strip() for p in line_stripped.split(",")]
            if not parts:
                continue

            # Detect header: must contain Start_Date and End_Date
            if "Start_Date" in parts and "End_Date" in parts:
                header_cols = parts
                start_idx = parts.index("Start_Date")
                end_idx = parts.index("End_Date")
                if start_idx < 0 or end_idx < 0 or start_idx >= len(parts) or end_idx >= len(parts):
                    raise ProcessorError(
                        "Uperf results require timestamps. CSV header must include "
                        "Start_Date and End_Date columns."
                    )
                continue

            if start_idx is None or end_idx is None:
                raise ProcessorError(
                    "Uperf results require timestamps. No header line with Start_Date and End_Date found. "
                    "Expected comma-delimited header: number_procs,Gb_Sec,...,Start_Date,End_Date"
                )

            if len(parts) <= max(start_idx, end_idx):
                raise ProcessorError(
                    f"Uperf CSV row has too few columns (got {len(parts)}, need Start_Date at index {start_idx}, "
                    f"End_Date at {end_idx}). Row: {line_stripped[:80]!r}..."
                )

            start_ts = parts[start_idx]
            end_ts = parts[end_idx]
            start_timestamp = _validate_iso8601_timestamp(
                start_ts, f"Row with number_procs={parts[0] if parts else '?'}:"
            )
            end_timestamp = _validate_iso8601_timestamp(
                end_ts, f"Row with number_procs={parts[0] if parts else '?'}:"
            )

            # Map header to indices for number_procs, Gb_Sec, trans_sec, lat_usec, test_type, packet_type, packet_size
            def col(name: str) -> int:
                if name in header_cols:
                    return header_cols.index(name)
                return -1

            num_procs_idx = col("number_procs")
            gb_sec_idx = col("Gb_Sec")
            trans_sec_idx = col("trans_sec")
            lat_usec_idx = col("lat_usec")
            test_type_idx = col("test_type")
            packet_type_idx = col("packet_type")
            packet_size_idx = col("packet_size")

            number_procs = int(parts[num_procs_idx]) if num_procs_idx >= 0 and num_procs_idx < len(parts) else 0
            try:
                gb_sec = float(parts[gb_sec_idx]) if gb_sec_idx >= 0 and gb_sec_idx < len(parts) else None
            except (ValueError, IndexError):
                gb_sec = None
            try:
                trans_sec = float(parts[trans_sec_idx]) if trans_sec_idx >= 0 and trans_sec_idx < len(parts) else None
            except (ValueError, IndexError):
                trans_sec = None
            try:
                lat_usec = float(parts[lat_usec_idx]) if lat_usec_idx >= 0 and lat_usec_idx < len(parts) else None
            except (ValueError, IndexError):
                lat_usec = None
            test_type = parts[test_type_idx] if test_type_idx >= 0 and test_type_idx < len(parts) else ""
            packet_type = parts[packet_type_idx] if packet_type_idx >= 0 and packet_type_idx < len(parts) else ""
            packet_size_str = parts[packet_size_idx] if packet_size_idx >= 0 and packet_size_idx < len(parts) else "0"
            try:
                packet_size_int = int(packet_size_str)
            except ValueError:
                packet_size_int = 0

            config_key = f"{test_type}_{packet_type}_{packet_size_str}"
            if config_key not in run_data["configurations"]:
                run_data["configurations"][config_key] = {
                    "test_type": test_type,
                    "protocol": packet_type,
                    "packet_size_bytes": packet_size_int,
                    "data_points": [],
                    "throughput_values": [],
                }
            if gb_sec is not None:
                run_data["overall_metrics"].setdefault(f"{config_key}_max_throughput_gbps", gb_sec)
                run_data["overall_metrics"][f"{config_key}_max_throughput_gbps"] = max(
                    run_data["overall_metrics"][f"{config_key}_max_throughput_gbps"], gb_sec
                )
                all_throughput_values.append(gb_sec)
            run_data["configurations"][config_key]["data_points"].append({
                "instance_count": number_procs,
                "iops": trans_sec,
                "latency_usec": lat_usec,
                "throughput_gbps": gb_sec,
            })
            run_data["configurations"][config_key]["throughput_values"].extend(
                [gb_sec] if gb_sec is not None else []
            )

            seq_key = create_sequence_key(sequence)
            run_data["timeseries"][seq_key] = {
                "timestamp": start_timestamp,
                "metrics": {
                    "configuration": config_key,
                    "test_type": test_type,
                    "protocol": packet_type,
                    "packet_size_bytes": packet_size_int,
                    "instance_count": number_procs,
                    "iops": trans_sec,
                    "latency_usec": lat_usec,
                    "throughput_gbps": gb_sec,
                },
            }
            sequence += 1

        if all_throughput_values:
            run_data["overall_metrics"]["total_configurations"] = len(run_data["configurations"])
            run_data["overall_metrics"]["peak_throughput_gbps"] = max(all_throughput_values)
            run_data["overall_metrics"]["mean_throughput_gbps"] = statistics.mean(all_throughput_values)

        return run_data

    def _parse_uperf_net_results(self, net_results_dir: Path) -> Dict[str, Any]:
        """
        Parse Uperf results from net_results directory layout.

        Requires run-level timestamps in net_results_dir/run_metadata.csv with format:
          Start_Date,End_Date
          2026-02-10T14:40:00Z,2026-02-10T14:50:00Z
        Timestamps are interpolated for each data point. Raises ProcessorError if
        run_metadata is missing or timestamps are invalid.
        """
        run_metadata_file = net_results_dir / "run_metadata.csv"
        if not run_metadata_file.exists():
            raise ProcessorError(
                "Uperf results require timestamps. When using net_results layout, "
                "run_metadata.csv with Start_Date,End_Date (ISO 8601) is required in net_results."
            )
        start_ts, end_ts = self._read_run_metadata_timestamps(run_metadata_file)

        run_data = {
            "run_number": 0,
            "status": "PASS",
            "configurations": {},
            "timeseries": {},
            "overall_metrics": {},
        }
        sequence = 0
        all_throughput_values: List[float] = []
        data_points_ordered: List[Dict[str, Any]] = []

        for test_type_dir in net_results_dir.iterdir():
            if not test_type_dir.is_dir():
                continue
            test_type = test_type_dir.name
            for protocol_dir in test_type_dir.iterdir():
                if not protocol_dir.is_dir():
                    continue
                protocol = protocol_dir.name
                for packet_size_dir in protocol_dir.iterdir():
                    if not packet_size_dir.is_dir():
                        continue
                    packet_size = packet_size_dir.name
                    iteration_dirs = [d for d in packet_size_dir.iterdir() if d.is_dir()]
                    if not iteration_dirs:
                        continue
                    result_dir = iteration_dirs[0]
                    config_key = f"{test_type}_{protocol}_{packet_size}"
                    config_data = self._parse_config_csvs(result_dir, test_type, protocol, packet_size)
                    if config_data:
                        run_data["configurations"][config_key] = config_data
                        if config_data.get("throughput_values"):
                            run_data["overall_metrics"][f"{config_key}_max_throughput_gbps"] = max(
                                config_data["throughput_values"]
                            )
                            all_throughput_values.extend(config_data["throughput_values"])
                        for point_data in config_data.get("data_points", []):
                            data_points_ordered.append({
                                "config_key": config_key,
                                "test_type": test_type,
                                "protocol": protocol,
                                "packet_size": packet_size,
                                "point_data": point_data,
                            })

        n = len(data_points_ordered)
        if n == 0:
            raise ProcessorError(
                "Uperf net_results: no data points found. Ensure iops.csv, latency.csv, throughput.csv exist."
            )
        start_dt = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
        for i, item in enumerate(data_points_ordered):
            if n <= 1:
                ts_str = start_ts
            else:
                frac = i / (n - 1)
                delta_sec = (end_dt - start_dt).total_seconds() * frac
                point_dt = start_dt + timedelta(seconds=delta_sec)
                ts_str = (
                    point_dt.strftime("%Y-%m-%dT%H:%M:%S")
                    + (f".{point_dt.microsecond:06d}".rstrip("0").rstrip(".") or "")
                    + "Z"
                )
            seq_key = create_sequence_key(sequence)
            pd = item["point_data"]
            run_data["timeseries"][seq_key] = {
                "timestamp": ts_str,
                "metrics": {
                    "configuration": item["config_key"],
                    "test_type": item["test_type"],
                    "protocol": item["protocol"],
                    "packet_size_bytes": int(item["packet_size"]),
                    "instance_count": pd["instance_count"],
                    "iops": pd.get("iops"),
                    "latency_usec": pd.get("latency_usec"),
                    "throughput_gbps": pd.get("throughput_gbps"),
                },
            }
            sequence += 1

        if all_throughput_values:
            run_data["overall_metrics"]["total_configurations"] = len(run_data["configurations"])
            run_data["overall_metrics"]["peak_throughput_gbps"] = max(all_throughput_values)
            run_data["overall_metrics"]["mean_throughput_gbps"] = statistics.mean(all_throughput_values)

        return run_data

    def _read_run_metadata_timestamps(self, metadata_file: Path) -> tuple:
        """Read Start_Date,End_Date from run_metadata.csv. Raises ProcessorError if missing/invalid."""
        content = read_file_content(metadata_file)
        lines = [ln.strip() for ln in content.strip().split("\n") if ln.strip() and not ln.strip().startswith("#")]
        if len(lines) < 2:
            raise ProcessorError(
                "Uperf run_metadata.csv must have a header line (Start_Date,End_Date) and a data line with ISO 8601 timestamps."
            )
        parts = [p.strip() for p in lines[1].split(",")]
        if len(parts) < 2:
            raise ProcessorError(
                "Uperf run_metadata.csv data line must have at least two columns: Start_Date,End_Date."
            )
        start_ts = _validate_iso8601_timestamp(parts[0], "run_metadata.csv Start_Date:")
        end_ts = _validate_iso8601_timestamp(parts[1], "run_metadata.csv End_Date:")
        return start_ts, end_ts

    def _parse_config_csvs(
        self, result_dir: Path, test_type: str, protocol: str, packet_size: str
    ) -> Optional[Dict[str, Any]]:
        """
        Parse the 3 CSV files for a single configuration.

        Returns dict with:
        - data_points: List of dicts with instance_count, iops, latency_usec, throughput_gbps
        - throughput_values: List of throughput values for stats
        """
        iops_file = result_dir / "iops.csv"
        latency_file = result_dir / "latency.csv"
        throughput_file = result_dir / "throughput.csv"

        if not all([f.exists() for f in [iops_file, latency_file, throughput_file]]):
            logger.warning(f"Missing CSV files in {result_dir}")
            return None

        try:
            # Parse each CSV
            iops_data = self._parse_csv_file(iops_file)
            latency_data = self._parse_csv_file(latency_file)
            throughput_data = self._parse_csv_file(throughput_file)

            # Merge data by instance count
            data_points = []
            throughput_values = []

            all_instances = set(iops_data.keys()) | set(latency_data.keys()) | set(throughput_data.keys())
            for instance_count in sorted(all_instances):
                point = {
                    "instance_count": instance_count,
                    "iops": iops_data.get(instance_count),
                    "latency_usec": latency_data.get(instance_count),
                    "throughput_gbps": throughput_data.get(instance_count)
                }
                data_points.append(point)

                if point["throughput_gbps"] is not None:
                    throughput_values.append(point["throughput_gbps"])

            return {
                "test_type": test_type,
                "protocol": protocol,
                "packet_size_bytes": int(packet_size),
                "data_points": data_points,
                "throughput_values": throughput_values
            }

        except Exception as e:
            logger.error(f"Failed to parse CSVs in {result_dir}: {e}")
            return None

    def _parse_csv_file(self, csv_file: Path) -> Dict[int, float]:
        """
        Parse a Uperf CSV file.

        Format:
        Instance_Count:metric
        1:40812:rr:tcp:1024
        2:141:rr:tcp:1024
        ...

        Returns dict mapping instance_count -> value
        """
        data = {}

        content = read_file_content(csv_file)
        lines = content.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line or line.startswith('Instance_Count'):
                continue

            parts = line.split(':')
            if len(parts) >= 2:
                try:
                    instance_count = int(parts[0])
                    value = float(parts[1])
                    data[instance_count] = value
                except (ValueError, IndexError):
                    continue

        return data

    def _build_run_object(self, run_data: Dict[str, Any]) -> Run:
        """Convert raw run data dictionary to Run dataclass object.

        Requires valid timestamps for every timeseries point; raises ProcessorError if any are missing or invalid.
        """
        timeseries = {}
        if "timeseries" in run_data and run_data["timeseries"]:
            for seq_key, ts_data in run_data["timeseries"].items():
                ts = ts_data.get("timestamp")
                if not ts:
                    raise ProcessorError(
                        f"Uperf run timeseries point {seq_key} is missing a timestamp. "
                        "Timestamps must come from the CSV Start_Date/End_Date or run_metadata."
                    )
                _validate_iso8601_timestamp(ts, f"Timeseries {seq_key}:")
                timeseries[seq_key] = TimeSeriesPoint(
                    timestamp=ts,
                    metrics=ts_data.get("metrics", {}),
                )

        # Calculate time series summary using throughput as primary metric
        ts_summary = None
        if timeseries:
            # Extract throughput values for summary stats
            throughput_values = []
            for ts_point in timeseries.values():
                if "throughput_gbps" in ts_point.metrics and ts_point.metrics["throughput_gbps"] is not None:
                    throughput_values.append(ts_point.metrics["throughput_gbps"])

            if throughput_values:
                ts_summary = TimeSeriesSummary(
                    mean=statistics.mean(throughput_values),
                    median=statistics.median(throughput_values),
                    min=min(throughput_values),
                    max=max(throughput_values),
                    stddev=statistics.stdev(throughput_values) if len(throughput_values) > 1 else 0.0,
                    count=len(throughput_values)
                )

        # Create Run object
        return Run(
            run_number=run_data.get("run_number", 0),
            status=run_data.get("status", "UNKNOWN"),
            metrics=run_data.get("overall_metrics", {}),
            configuration={
                # Sort lists for deterministic ordering (important for content hash)
                "test_types": sorted(list(set(
                    c["test_type"] for c in run_data.get("configurations", {}).values()
                ))),
                "protocols": sorted(list(set(
                    c["protocol"] for c in run_data.get("configurations", {}).values()
                ))),
                "packet_sizes": sorted(list(set(
                    c["packet_size_bytes"] for c in run_data.get("configurations", {}).values()
                )))
            },
            timeseries=timeseries if timeseries else None,
            timeseries_summary=ts_summary
        )
