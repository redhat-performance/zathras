"""
Uperf processor for Zathras results.

Uperf is a network performance tool that measures throughput, latency, and transaction rate
across various protocols, packet sizes, and concurrency levels.
"""

from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import logging
import statistics

from .base_processor import BaseProcessor
from ..schema import Run, TimeSeriesPoint, TimeSeriesSummary, create_run_key, create_sequence_key
from ..utils.parser_utils import read_file_content

logger = logging.getLogger(__name__)


class UperfProcessor(BaseProcessor):
    """Processor for Uperf network performance benchmark results."""

    def get_test_name(self) -> str:
        return "uperf"

    def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Run]:
        """
        Parse Uperf runs into object-based structure.

        Uperf runs multiple test configurations (test type x protocol x packet size)
        and measures IOPS, latency, and throughput at different concurrency levels.

        We'll treat this as a single run with:
        - Aggregated metrics for all configurations
        - Each configuration's concurrency sweep as time series points

        Returns:
            A dictionary of Run objects, keyed by run_key (typically just "run_0").
        """
        extracted_path = Path(extracted_result['extracted_path'])

        # Find the net_results directory
        net_results_dirs = list(extracted_path.rglob("net_results"))

        if not net_results_dirs:
            logger.error(f"No net_results directory found in {extracted_path}")
            return {}

        net_results_dir = net_results_dirs[0]

        # Parse all test configurations
        run_data = self._parse_uperf_results(net_results_dir)

        # Build Run object
        run_objects = {}
        if run_data:
            run_objects[create_run_key(0)] = self._build_run_object(run_data)

        logger.info(f"Parsed Uperf: 1 run with {len(run_data.get('configurations', {}))} configurations")
        return run_objects

    def _parse_uperf_results(self, net_results_dir: Path) -> Dict[str, Any]:
        """
        Parse Uperf network results.

        Structure: net_results/<test_type>/<protocol>/<packet_size>/1/
        - test_type: rr (request-response), stream
        - protocol: tcp
        - packet_size: 64, 1024, 16384

        Each configuration has 3 CSV files:
        - iops.csv: Transactions per second
        - latency.csv: Latency in microseconds
        - throughput.csv: Throughput in GB/sec
        """
        run_data = {
            "run_number": 0,
            "status": "PASS",
            "configurations": {},
            "timeseries": {},
            "overall_metrics": {}
        }

        sequence = 0
        all_throughput_values = []

        # Iterate through test types
        for test_type_dir in net_results_dir.iterdir():
            if not test_type_dir.is_dir():
                continue

            test_type = test_type_dir.name  # e.g., "rr", "stream"

            # Iterate through protocols
            for protocol_dir in test_type_dir.iterdir():
                if not protocol_dir.is_dir():
                    continue

                protocol = protocol_dir.name  # e.g., "tcp"

                # Iterate through packet sizes
                for packet_size_dir in protocol_dir.iterdir():
                    if not packet_size_dir.is_dir():
                        continue

                    packet_size = packet_size_dir.name  # e.g., "1024"

                    # Find the iteration directory (usually "1")
                    iteration_dirs = [d for d in packet_size_dir.iterdir() if d.is_dir()]
                    if not iteration_dirs:
                        continue

                    result_dir = iteration_dirs[0]

                    # Parse the 3 CSV files
                    config_key = f"{test_type}_{protocol}_{packet_size}"
                    config_data = self._parse_config_csvs(result_dir, test_type, protocol, packet_size)

                    if config_data:
                        run_data["configurations"][config_key] = config_data

                        # Store overall metrics for this configuration
                        if config_data.get("throughput_values"):
                            throughput_values = config_data["throughput_values"]
                            max_throughput = max(throughput_values)
                            run_data["overall_metrics"][f"{config_key}_max_throughput_gbps"] = max_throughput
                            all_throughput_values.extend(throughput_values)

                        # Create time series points for this configuration
                        # Each instance count is a separate point
                        if config_data.get("data_points"):
                            for point_data in config_data["data_points"]:
                                seq_key = create_sequence_key(sequence)
                                run_data["timeseries"][seq_key] = {
                                    "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    "metrics": {
                                        "configuration": config_key,
                                        "test_type": test_type,
                                        "protocol": protocol,
                                        "packet_size_bytes": int(packet_size),
                                        "instance_count": point_data["instance_count"],
                                        "iops": point_data.get("iops"),
                                        "latency_usec": point_data.get("latency_usec"),
                                        "throughput_gbps": point_data.get("throughput_gbps")
                                    }
                                }
                                sequence += 1

        # Calculate overall statistics
        if all_throughput_values:
            run_data["overall_metrics"]["total_configurations"] = len(run_data["configurations"])
            run_data["overall_metrics"]["peak_throughput_gbps"] = max(all_throughput_values)
            run_data["overall_metrics"]["mean_throughput_gbps"] = statistics.mean(all_throughput_values)

        return run_data

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
        """Convert raw run data dictionary to Run dataclass object."""

        # Convert timeseries dictionary to TimeSeriesPoint objects
        timeseries = {}
        if "timeseries" in run_data and run_data["timeseries"]:
            for seq_key, ts_data in run_data["timeseries"].items():
                timeseries[seq_key] = TimeSeriesPoint(
                    timestamp=ts_data.get("timestamp", datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")),
                    metrics=ts_data.get("metrics", {})
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
