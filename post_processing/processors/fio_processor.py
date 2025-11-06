import json
import re
import statistics
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta
import logging

from .base_processor import BaseProcessor
from ..schema import (
    Run, TimeSeriesPoint, TimeSeriesSummary, PrimaryMetric,
    create_run_key, create_sequence_key
)
from ..utils.parser_utils import (
    parse_version_file,
    read_file_content
)

logger = logging.getLogger(__name__)


class FioProcessor(BaseProcessor):
    """
    Processor for FIO (Flexible I/O Tester) benchmark results.

    Handles multi-disk, multi-job configurations with comprehensive metrics.
    Aggregates results across all jobs while preserving per-job details.
    """

    def get_test_name(self) -> str:
        return "fio"

    def build_results(self) -> Any:
        """
        Build Results object with overall primary metric.

        Primary metric is the maximum bandwidth achieved across all workloads.

        Returns:
            Results object
        """
        # Call parent to build basic Results object
        results = super().build_results()

        if not results or not results.runs:
            return results

        # Find the run with the highest bandwidth
        max_bw = 0
        max_bw_run = None

        for run_key, run in results.runs.items():
            bw = run.metrics.get('total_bandwidth_kbps', 0)
            if bw > max_bw:
                max_bw = bw
                max_bw_run = run

        # Set primary metric
        if max_bw_run and max_bw > 0:
            results.primary_metric = PrimaryMetric(
                name='max_bandwidth',
                value=max_bw,
                unit='KiB/s'
            )

        return results

    def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse FIO runs into object-based structure.

        Each workload test (e.g., read-4KiB) becomes one Run with aggregated metrics.

        Returns:
            {
                "run_0": {run_data for workload 0},
                "run_1": {run_data for workload 1},
                ...
            }
        """
        result_dir = Path(extracted_result['extracted_path'])

        # Find the export_fio_data directory
        export_dirs = list(result_dir.glob("export_fio_data_*"))
        if not export_dirs:
            logger.warning(f"No export_fio_data_* directory found in {result_dir}")
            return {}

        export_dir = export_dirs[0]
        logger.debug(f"Found FIO export directory: {export_dir}")

        # Parse version
        version_file = result_dir / "version"
        version = parse_version_file(version_file) if version_file.exists() else None

        # Parse test status
        status_file = export_dir / "test_results_report"
        test_status = "PASS" if status_file.exists() and "Ran" in read_file_content(status_file) else "UNKNOWN"

        # Find all configuration directories
        config_dirs = sorted(export_dir.glob("fio_ndisks_*"))
        if not config_dirs:
            logger.warning(f"No fio_ndisks_* directories found in {export_dir}")
            return {}

        logger.info(f"Found {len(config_dirs)} FIO configuration directories")

        runs = {}
        run_number = 0

        # Process each configuration directory
        for config_dir in config_dirs:
            # Parse configuration from directory name
            config_info = self._parse_config_dir_name(config_dir.name)

            # Find all workload subdirectories (e.g., 1-read-4KiB, 2-write-4KiB)
            workload_dirs = sorted([d for d in config_dir.iterdir() if d.is_dir() and d.name[0].isdigit()])

            for workload_dir in workload_dirs:
                logger.debug(f"Processing workload: {workload_dir.name}")

                # Parse the JSON file (primary source)
                json_file = workload_dir / "fio-results.json"
                if not json_file.exists():
                    logger.warning(f"No fio-results.json in {workload_dir}")
                    continue

                try:
                    with open(json_file, 'r') as f:
                        fio_data = json.load(f)

                    # Build run object
                    run_data = self._build_run_object(
                        run_number=run_number,
                        fio_data=fio_data,
                        workload_dir=workload_dir,
                        config_info=config_info,
                        status=test_status,
                        version=version
                    )

                    runs[create_run_key(run_number)] = run_data
                    run_number += 1

                except Exception as e:
                    logger.error(f"Failed to process {workload_dir.name}: {e}")
                    continue

        logger.info(f"Parsed {len(runs)} FIO workload runs")
        return runs

    def _parse_config_dir_name(self, dir_name: str) -> Dict[str, Any]:
        """
        Parse configuration from directory name.

        Example: fio_ndisks_2_disksize_2.93_TiB_njobs_1_ioengine_libaio_iodepth_16_2025.03.13T00.20.02
        """
        config = {}

        # Extract ndisks
        ndisks_match = re.search(r'ndisks_(\d+)', dir_name)
        if ndisks_match:
            config['ndisks'] = int(ndisks_match.group(1))

        # Extract disksize
        disksize_match = re.search(r'disksize_([\d.]+)_(\w+)', dir_name)
        if disksize_match:
            config['disksize'] = f"{disksize_match.group(1)} {disksize_match.group(2)}"

        # Extract njobs
        njobs_match = re.search(r'njobs_(\d+)', dir_name)
        if njobs_match:
            config['njobs'] = int(njobs_match.group(1))

        # Extract ioengine
        ioengine_match = re.search(r'ioengine_(\w+)', dir_name)
        if ioengine_match:
            config['ioengine'] = ioengine_match.group(1)

        # Extract iodepth
        iodepth_match = re.search(r'iodepth_(\d+)', dir_name)
        if iodepth_match:
            config['iodepth'] = int(iodepth_match.group(1))

        # Extract timestamp
        timestamp_match = re.search(r'(\d{4}\.\d{2}\.\d{2}T\d{2}\.\d{2}\.\d{2})$', dir_name)
        if timestamp_match:
            config['timestamp_str'] = timestamp_match.group(1)

        return config

    def _parse_workload_dir_name(self, dir_name: str) -> Dict[str, Any]:
        """
        Parse workload information from directory name.

        Example: 1-read-4KiB, 2-write-4KiB, 3-read-1024KiB
        """
        workload = {}

        # Extract sequence number
        seq_match = re.match(r'(\d+)-', dir_name)
        if seq_match:
            workload['sequence'] = int(seq_match.group(1))

        # Extract operation
        if 'read' in dir_name.lower():
            workload['operation'] = 'read'
        elif 'write' in dir_name.lower():
            workload['operation'] = 'write'
        else:
            workload['operation'] = 'unknown'

        # Extract block size
        bs_match = re.search(r'(\d+)(KiB|MiB|GiB)', dir_name)
        if bs_match:
            workload['block_size'] = f"{bs_match.group(1)}{bs_match.group(2)}"
            # Convert to bytes
            size = int(bs_match.group(1))
            unit = bs_match.group(2)
            multiplier = {'KiB': 1024, 'MiB': 1024*1024, 'GiB': 1024*1024*1024}
            workload['block_size_bytes'] = size * multiplier.get(unit, 1024)

        return workload

    def _build_run_object(
        self,
        run_number: int,
        fio_data: Dict[str, Any],
        workload_dir: Path,
        config_info: Dict[str, Any],
        status: str,
        version: Optional[str]
    ) -> Run:
        """Build a Run object for one FIO workload test."""

        # Parse workload info from directory name
        workload_info = self._parse_workload_dir_name(workload_dir.name)

        # Extract jobs array
        jobs = fio_data.get('jobs', [])
        if not jobs:
            logger.warning(f"No jobs found in {workload_dir}")
            return Run(run_number=run_number, status="FAIL", metrics={}, configuration={})

        # Determine operation type
        operation = workload_info.get('operation', 'unknown')

        # Build aggregated metrics
        aggregated_metrics = self._aggregate_metrics(jobs, operation)

        # Add per-job breakdown
        aggregated_metrics['jobs'] = [
            self._build_job_metrics(job, i, operation)
            for i, job in enumerate(jobs)
        ]

        # Add disk utilization
        if 'disk_util' in fio_data:
            aggregated_metrics['disk_utilization'] = fio_data['disk_util']

        # Add metadata
        aggregated_metrics['num_jobs'] = len(jobs)
        aggregated_metrics['num_disks'] = config_info.get('ndisks', len(jobs))

        # Build configuration
        configuration = self._build_configuration(
            fio_data.get('global options', {}),
            workload_info,
            config_info,
            jobs,
            version
        )

        # Parse time series
        timeseries, ts_summary = self._parse_timeseries(
            workload_dir,
            len(jobs),
            operation,
            fio_data.get('timestamp', None)
        )

        return Run(
            run_number=run_number,
            status=status,
            metrics=aggregated_metrics,
            configuration=configuration,
            timeseries=timeseries if timeseries else None,
            timeseries_summary=ts_summary
        )

    def _aggregate_metrics(self, jobs: List[Dict[str, Any]], operation: str) -> Dict[str, Any]:
        """
        Aggregate metrics across all jobs.

        - Bandwidth/IOPS: Sum across jobs
        - Latency: Weighted average by I/O count
        - CPU/System: Simple average
        """
        metrics = {}

        # Collect operation-specific data from all jobs
        job_data = []
        total_ios = 0

        for job in jobs:
            op_data = job.get(operation, {})
            if op_data and op_data.get('io_bytes', 0) > 0:
                job_data.append(op_data)
                total_ios += op_data.get('total_ios', 0)

        if not job_data:
            logger.warning(f"No active {operation} operations found in jobs")
            return metrics

        # Aggregate bandwidth (sum)
        metrics['total_bandwidth_kbps'] = sum(jd.get('bw', 0) for jd in job_data)
        metrics['total_bandwidth_min'] = sum(jd.get('bw_min', 0) for jd in job_data)
        metrics['total_bandwidth_max'] = sum(jd.get('bw_max', 0) for jd in job_data)

        # Bandwidth statistics (from samples, average across jobs)
        bw_means = [jd.get('bw_mean', 0) for jd in job_data if 'bw_mean' in jd]
        if bw_means:
            metrics['total_bandwidth_mean'] = sum(bw_means)
            if len(bw_means) > 1:
                metrics['total_bandwidth_stddev'] = statistics.stdev(bw_means)

        # Aggregate IOPS (sum)
        metrics['total_iops'] = sum(jd.get('iops', 0) for jd in job_data)
        metrics['total_iops_min'] = sum(jd.get('iops_min', 0) for jd in job_data)
        metrics['total_iops_max'] = sum(jd.get('iops_max', 0) for jd in job_data)

        # IOPS statistics
        iops_means = [jd.get('iops_mean', 0) for jd in job_data if 'iops_mean' in jd]
        if iops_means:
            metrics['total_iops_mean'] = sum(iops_means)

        # Aggregate latency (weighted average)
        if total_ios > 0:
            lat_ns = [jd.get('lat_ns', {}) for jd in job_data]

            weighted_lat_mean = sum(
                lat.get('mean', 0) * jd.get('total_ios', 0)
                for lat, jd in zip(lat_ns, job_data)
            ) / total_ios

            metrics['avg_latency_mean_ns'] = weighted_lat_mean
            metrics['avg_latency_min_ns'] = min(lat.get('min', 0) for lat in lat_ns if 'min' in lat)
            metrics['avg_latency_max_ns'] = max(lat.get('max', 0) for lat in lat_ns if 'max' in lat)

            # Weighted stddev
            weighted_lat_stddev = sum(
                lat.get('stddev', 0) * jd.get('total_ios', 0)
                for lat, jd in zip(lat_ns, job_data)
            ) / total_ios
            metrics['avg_latency_stddev_ns'] = weighted_lat_stddev

            # Aggregate completion latency (clat)
            clat_ns = [jd.get('clat_ns', {}) for jd in job_data]
            weighted_clat_mean = sum(
                clat.get('mean', 0) * jd.get('total_ios', 0)
                for clat, jd in zip(clat_ns, job_data)
            ) / total_ios
            metrics['avg_clat_mean_ns'] = weighted_clat_mean
            metrics['avg_clat_min_ns'] = min(clat.get('min', 0) for clat in clat_ns if 'min' in clat)
            metrics['avg_clat_max_ns'] = max(clat.get('max', 0) for clat in clat_ns if 'max' in clat)

            # Aggregate submission latency (slat)
            slat_ns = [jd.get('slat_ns', {}) for jd in job_data]
            weighted_slat_mean = sum(
                slat.get('mean', 0) * jd.get('total_ios', 0)
                for slat, jd in zip(slat_ns, job_data)
            ) / total_ios
            metrics['avg_slat_mean_ns'] = weighted_slat_mean
            metrics['avg_slat_min_ns'] = min(slat.get('min', 0) for slat in slat_ns if 'min' in slat)
            metrics['avg_slat_max_ns'] = max(slat.get('max', 0) for slat in slat_ns if 'max' in slat)

            # Aggregate percentiles (weighted average)
            percentiles = [
                '1.000000', '5.000000', '10.000000', '50.000000',
                '90.000000', '95.000000', '99.000000', '99.500000', '99.900000'
            ]
            percentile_names = ['p1', 'p5', 'p10', 'p50', 'p90', 'p95', 'p99', 'p99_5', 'p99_9']

            for pct, name in zip(percentiles, percentile_names):
                weighted_pct = sum(
                    clat.get('percentile', {}).get(pct, 0) * jd.get('total_ios', 0)
                    for clat, jd in zip(clat_ns, job_data)
                ) / total_ios
                metrics[f'avg_latency_{name}_ns'] = weighted_pct

        # Aggregate I/O statistics (sum)
        metrics['total_io_bytes'] = sum(jd.get('io_bytes', 0) for jd in job_data)
        metrics['total_ios'] = total_ios

        # Average runtime
        runtimes = [jd.get('runtime', 0) for jd in job_data if 'runtime' in jd]
        if runtimes:
            metrics['avg_runtime_ms'] = statistics.mean(runtimes)

        # Aggregate CPU metrics (average)
        cpu_usr = [job.get('usr_cpu', 0) for job in jobs]
        cpu_sys = [job.get('sys_cpu', 0) for job in jobs]
        if cpu_usr:
            metrics['avg_cpu_usr_pct'] = statistics.mean(cpu_usr)
        if cpu_sys:
            metrics['avg_cpu_sys_pct'] = statistics.mean(cpu_sys)

        return metrics

    def _build_job_metrics(self, job: Dict[str, Any], job_number: int, operation: str) -> Dict[str, Any]:
        """Build detailed metrics for a single job."""
        job_metrics = {
            'job_number': job_number,
            'jobname': job.get('jobname', f'job-{job_number}'),
            'groupid': job.get('groupid', 0),
            'elapsed_seconds': job.get('elapsed', 0)
        }

        # Extract device from job options
        job_options = job.get('job options', {})
        if 'filename' in job_options:
            job_metrics['device'] = job_options['filename']

        # Add operation-specific metrics
        for op in ['read', 'write']:
            op_data = job.get(op, {})
            if op_data and op_data.get('io_bytes', 0) > 0:
                job_metrics[op] = self._extract_operation_metrics(op_data)
            else:
                job_metrics[op] = None

        # Add system metrics
        job_metrics['cpu_usr_pct'] = job.get('usr_cpu', 0)
        job_metrics['cpu_sys_pct'] = job.get('sys_cpu', 0)

        # Add I/O depth distribution
        if 'iodepth_level' in job:
            job_metrics['iodepth_distribution'] = {
                '1': job['iodepth_level'].get('1', 0),
                '2': job['iodepth_level'].get('2', 0),
                '4': job['iodepth_level'].get('4', 0),
                '8': job['iodepth_level'].get('8', 0),
                '16': job['iodepth_level'].get('16', 0),
                '32': job['iodepth_level'].get('32', 0),
                '64_or_more': job['iodepth_level'].get('>=64', 0)
            }

        # Add latency distribution
        if 'latency_us' in job:
            job_metrics['latency_distribution_us'] = job['latency_us']
        if 'latency_ms' in job:
            job_metrics['latency_distribution_ms'] = job['latency_ms']

        return job_metrics

    def _extract_operation_metrics(self, op_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract metrics for a specific operation (read or write)."""
        metrics = {
            'bandwidth_kbps': op_data.get('bw', 0),
            'bandwidth_min': op_data.get('bw_min', 0),
            'bandwidth_max': op_data.get('bw_max', 0),
            'bandwidth_mean': op_data.get('bw_mean', 0),
            'bandwidth_stddev': op_data.get('bw_dev', 0),
            'bandwidth_agg_pct': op_data.get('bw_agg', 0),

            'iops': op_data.get('iops', 0),
            'iops_min': op_data.get('iops_min', 0),
            'iops_max': op_data.get('iops_max', 0),
            'iops_mean': op_data.get('iops_mean', 0),
            'iops_stddev': op_data.get('iops_stddev', 0),

            'io_bytes': op_data.get('io_bytes', 0),
            'total_ios': op_data.get('total_ios', 0),
            'runtime_ms': op_data.get('runtime', 0)
        }

        # Add latency metrics
        lat_ns = op_data.get('lat_ns', {})
        if lat_ns:
            metrics['latency_mean_ns'] = lat_ns.get('mean', 0)
            metrics['latency_min_ns'] = lat_ns.get('min', 0)
            metrics['latency_max_ns'] = lat_ns.get('max', 0)
            metrics['latency_stddev_ns'] = lat_ns.get('stddev', 0)

        # Add completion latency
        clat_ns = op_data.get('clat_ns', {})
        if clat_ns:
            metrics['clat_mean_ns'] = clat_ns.get('mean', 0)
            metrics['clat_min_ns'] = clat_ns.get('min', 0)
            metrics['clat_max_ns'] = clat_ns.get('max', 0)
            metrics['clat_stddev_ns'] = clat_ns.get('stddev', 0)

            # Add percentiles
            percentiles = clat_ns.get('percentile', {})
            if percentiles:
                metrics['latency_percentiles'] = {
                    'p1': percentiles.get('1.000000', 0),
                    'p5': percentiles.get('5.000000', 0),
                    'p10': percentiles.get('10.000000', 0),
                    'p50': percentiles.get('50.000000', 0),
                    'p90': percentiles.get('90.000000', 0),
                    'p95': percentiles.get('95.000000', 0),
                    'p99': percentiles.get('99.000000', 0),
                    'p99_5': percentiles.get('99.500000', 0),
                    'p99_9': percentiles.get('99.900000', 0)
                }

        # Add submission latency
        slat_ns = op_data.get('slat_ns', {})
        if slat_ns:
            metrics['slat_mean_ns'] = slat_ns.get('mean', 0)
            metrics['slat_min_ns'] = slat_ns.get('min', 0)
            metrics['slat_max_ns'] = slat_ns.get('max', 0)
            metrics['slat_stddev_ns'] = slat_ns.get('stddev', 0)

        return metrics

    def _build_configuration(
        self,
        global_options: Dict[str, Any],
        workload_info: Dict[str, Any],
        config_info: Dict[str, Any],
        jobs: List[Dict[str, Any]],
        version: Optional[str]
    ) -> Dict[str, Any]:
        """Build configuration dictionary for a run."""
        config = {
            'operation': workload_info.get('operation', 'unknown'),
            'block_size': workload_info.get('block_size', 'unknown'),
            'block_size_bytes': workload_info.get('block_size_bytes', 0),

            'ndisks': config_info.get('ndisks', len(jobs)),
            'devices': [job.get('job options', {}).get('filename', '') for job in jobs],

            'ioengine': global_options.get('ioengine', config_info.get('ioengine', 'unknown')),
            'iodepth': int(global_options.get('iodepth', config_info.get('iodepth', 1))),
            'direct_io': global_options.get('direct') == '1',
            'sync': global_options.get('sync') == '1',
            'time_based': global_options.get('time_based') == '1',
            'runtime_seconds': int(global_options.get('runtime', 0)),
            'ramp_time_seconds': int(global_options.get('ramp_time', 0)),
            'clocksource': global_options.get('clocksource', 'unknown'),

            'numjobs_per_device': config_info.get('njobs', 1),
            'disksize': config_info.get('disksize', 'unknown')
        }

        if version:
            config['fio_version'] = version

        return config

    def _parse_timeseries(
        self,
        workload_dir: Path,
        num_jobs: int,
        operation: str,
        test_timestamp: Optional[int]
    ) -> Tuple[Optional[Dict[str, TimeSeriesPoint]], Optional[TimeSeriesSummary]]:
        """
        Parse time series log files for all jobs.

        Returns aggregated time series across all jobs.
        """
        # Read log files for all jobs
        all_bw = []
        all_iops = []
        all_lat = []
        all_clat = []
        all_slat = []

        for job_num in range(num_jobs):
            job_suffix = f".{job_num + 1}.log"

            bw_data = self._parse_log_file(workload_dir / f"fio_bw{job_suffix}")
            iops_data = self._parse_log_file(workload_dir / f"fio_iops{job_suffix}")
            lat_data = self._parse_log_file(workload_dir / f"fio_lat{job_suffix}")
            clat_data = self._parse_log_file(workload_dir / f"fio_clat{job_suffix}")
            slat_data = self._parse_log_file(workload_dir / f"fio_slat{job_suffix}")

            all_bw.append(bw_data)
            all_iops.append(iops_data)
            all_lat.append(lat_data)
            all_clat.append(clat_data)
            all_slat.append(slat_data)

        # Check if we have data
        if not all_bw or not all_bw[0]:
            return None, None

        # Determine number of samples (should be consistent across all logs)
        num_samples = len(all_bw[0])

        # Calculate base timestamp
        if test_timestamp:
            base_time = datetime.fromtimestamp(test_timestamp)
        else:
            base_time = datetime.now()

        # Build aggregated time series
        timeseries = {}
        total_bw_values = []

        for i in range(num_samples):
            # Calculate timestamp for this sample
            timestamp_ms = all_bw[0][i][0]  # Milliseconds from start
            sample_time = base_time + timedelta(milliseconds=timestamp_ms)

            # Aggregate metrics across jobs
            total_bw = sum(all_bw[j][i][1] for j in range(num_jobs) if i < len(all_bw[j]))
            total_iops = sum(all_iops[j][i][1] for j in range(num_jobs) if i < len(all_iops[j]))

            # Average latencies
            avg_lat = statistics.mean(all_lat[j][i][1] for j in range(num_jobs) if i < len(all_lat[j]))
            avg_clat = statistics.mean(all_clat[j][i][1] for j in range(num_jobs) if i < len(all_clat[j]))
            avg_slat = statistics.mean(all_slat[j][i][1] for j in range(num_jobs) if i < len(all_slat[j]))

            total_bw_values.append(total_bw)

            # Build per-job breakdown
            jobs_data = []
            for j in range(num_jobs):
                if i < len(all_bw[j]):
                    jobs_data.append({
                        'job_number': j,
                        'bandwidth_kbps': all_bw[j][i][1],
                        'iops': all_iops[j][i][1],
                        'latency_ns': all_lat[j][i][1],
                        'clat_ns': all_clat[j][i][1],
                        'slat_ns': all_slat[j][i][1]
                    })

            timeseries[create_sequence_key(i)] = TimeSeriesPoint(
                timestamp=sample_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                metrics={
                    'total_bandwidth_kbps': total_bw,
                    'total_iops': total_iops,
                    'avg_latency_ns': avg_lat,
                    'avg_clat_ns': avg_clat,
                    'avg_slat_ns': avg_slat,
                    'jobs': jobs_data
                }
            )

        # Calculate summary
        ts_summary = TimeSeriesSummary(
            count=num_samples,
            mean=statistics.mean(total_bw_values),
            min=min(total_bw_values),
            max=max(total_bw_values),
            stddev=statistics.stdev(total_bw_values) if len(total_bw_values) > 1 else 0,
            first_value=total_bw_values[0],
            last_value=total_bw_values[-1]
        )

        return timeseries, ts_summary

    def _parse_log_file(self, log_file: Path) -> List[Tuple[int, float]]:
        """
        Parse a FIO log file.

        Format: timestamp_ms, value, direction, block_size, offset
        Returns: [(timestamp_ms, value), ...]
        """
        if not log_file.exists():
            logger.debug(f"Log file not found: {log_file}")
            return []

        data = []
        content = read_file_content(log_file)

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parts = line.split(',')
            if len(parts) >= 2:
                try:
                    timestamp_ms = int(parts[0].strip())
                    value = float(parts[1].strip())
                    data.append((timestamp_ms, value))
                except (ValueError, IndexError) as e:
                    logger.debug(f"Could not parse log line: {line} - {e}")

        return data
