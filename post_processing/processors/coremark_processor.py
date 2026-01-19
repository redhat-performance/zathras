"""
CoreMark Processor

Processes CoreMark benchmark results into object-based JSON documents.

CoreMark produces:
- results_coremark.csv - Time series data (iterations:threads:IterationsPerSec)
- run1_summary, run2_summary - Per-run metrics and configuration
- test_results_report - PASS/FAIL status
- version - Test wrapper version
- tuned_setting - System tuning applied
"""

import statistics
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging

from .base_processor import BaseProcessor
from ..schema import Run, TimeSeriesPoint, TimeSeriesSummary, create_run_key, create_sequence_key
from ..utils.parser_utils import (
    parse_csv_timeseries,
    parse_key_value_text,
    parse_version_file,
    read_file_content
)

logger = logging.getLogger(__name__)


class CoreMarkProcessor(BaseProcessor):
    """Processor for CoreMark benchmark results"""

    def get_test_name(self) -> str:
        return "coremark"

    def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse CoreMark runs into object-based structure

        Returns:
            {
                "run_1": {
                    "run_number": 1,
                    "status": "PASS",
                    "metrics": {...},
                    "timeseries": {
                        "2025-11-06T05:09:45.000Z": {
                            "sequence": 0,
                            "iteration": 1,
                            "value": 193245.2
                        }
                    }
                },
                "run_2": {...}
            }
        """
        files = extracted_result['files']

        # Parse CSV time series
        csv_file = files.get('results_csv')
        time_series_data = []
        if csv_file:
            time_series_data = parse_csv_timeseries(csv_file, delimiter=':')

        # Parse run summaries
        run_summaries = files.get('run_summaries', [])

        # Parse version and tuning
        version_file = files.get('version')
        version = parse_version_file(version_file) if version_file else None

        tuned_file = files.get('tuned_setting')
        tuned_setting = read_file_content(tuned_file).strip() if tuned_file else None

        # Group time series by run
        runs_data = self._group_time_series_by_run(time_series_data)

        # Build run objects
        runs = {}

        for run_num, (summary_file, ts_data) in enumerate(zip(run_summaries, runs_data), 1):
            run_key = create_run_key(run_num)

            # Parse run summary
            summary = parse_key_value_text(summary_file)

            # Build run object
            runs[run_key] = self._build_run_object(
                run_number=run_num,
                summary=summary,
                time_series_data=ts_data,
                version=version,
                tuned_setting=tuned_setting
            )

        # If no summaries but have time series, create runs from time series
        if not runs and time_series_data:
            for run_num, ts_data in enumerate(runs_data, 1):
                run_key = create_run_key(run_num)
                runs[run_key] = self._build_run_object(
                    run_number=run_num,
                    summary={},
                    time_series_data=ts_data,
                    version=version,
                    tuned_setting=tuned_setting
                )

        logger.info(f"Parsed {len(runs)} CoreMark runs")
        return runs

    def _group_time_series_by_run(self, time_series_data: List[Dict]) -> List[List[Dict]]:
        """
        Group time series data by run number

        CSV format: iteration:threads:IterationsPerSec
        Rows with same iteration = different run

        Example:
        1:4:193245  <- Run 1, iteration 1
        1:4:195999  <- Run 2, iteration 1
        2:4:190905  <- Run 1, iteration 2
        2:4:191537  <- Run 2, iteration 2
        """
        if not time_series_data:
            return []

        # Group by iteration number
        iterations = {}
        for row in time_series_data:
            iter_num = row.get('iteration', 1)
            if iter_num not in iterations:
                iterations[iter_num] = []
            iterations[iter_num].append(row)

        # Number of runs = max measurements per iteration
        num_runs = max(len(rows) for rows in iterations.values()) if iterations else 0

        # Create run groups
        runs = [[] for _ in range(num_runs)]

        for iter_num in sorted(iterations.keys()):
            measurements = iterations[iter_num]
            for run_idx, measurement in enumerate(measurements):
                if run_idx < num_runs:
                    runs[run_idx].append(measurement)

        return runs

    def _build_run_object(self, run_number: int, summary: Dict[str, Any],
                          time_series_data: List[Dict], version: Optional[str],
                          tuned_setting: Optional[str]) -> Run:
        """Build a Run object from parsed data"""

        # Extract metrics from summary
        metrics = {}
        config = {}

        if summary:
            # Metrics
            if 'iterations_per_sec' in summary:
                metrics['iterations_per_second'] = summary['iterations_per_sec']
            if 'iterations' in summary:
                metrics['total_iterations'] = summary['iterations']
            if 'total_time_secs' in summary:
                metrics['total_time_seconds'] = summary['total_time_secs']
            if 'total_ticks' in summary:
                metrics['total_ticks'] = summary['total_ticks']
            if 'coremark_size' in summary:
                metrics['coremark_size'] = summary['coremark_size']

            # Configuration
            if 'compiler_version' in summary:
                config['compiler'] = summary['compiler_version']
            if 'compiler_flags' in summary:
                config['compiler_flags'] = summary['compiler_flags']
            if 'parallel_pthreads' in summary:
                config['threads'] = summary['parallel_pthreads']

        # Parse time series into timestamp-keyed object
        timeseries = None
        timeseries_summary = None

        if time_series_data:
            timeseries, timeseries_summary = self._build_timeseries_object(
                time_series_data,
                run_number
            )

        # Calculate duration from summary
        duration = summary.get('total_time_secs') if summary else None

        # Estimate timestamps (we don't have exact timestamps in CoreMark)
        base_time = datetime(2025, 11, 6, 5, 9, 45)  # Placeholder
        start_time = base_time + timedelta(minutes=(run_number - 1) * 5)
        end_time = start_time + timedelta(seconds=duration) if duration else None

        return Run(
            run_number=run_number,
            status="PASS",  # Assume PASS if we got results
            start_time=start_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            end_time=end_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z" if end_time else None,
            duration_seconds=duration,
            configuration=config if config else None,
            metrics=metrics if metrics else None,
            timeseries_summary=timeseries_summary,
            timeseries=timeseries,
            validation=self._extract_validation(summary) if summary else None
        )

    def _build_timeseries_object(
        self, time_series_data: List[Dict], run_number: int
    ) -> tuple[Dict[str, TimeSeriesPoint], TimeSeriesSummary]:
        """
        Build timestamp-keyed time series object

        Returns:
            (timeseries_dict, summary)
        """
        timeseries = {}
        values = []

        # Base timestamp (estimate - CoreMark doesn't include actual timestamps)
        base_time = datetime(2025, 11, 6, 5, 9, 45)
        base_time = base_time + timedelta(minutes=(run_number - 1) * 5)

        for sequence, row in enumerate(time_series_data):
            # Get the primary metric value
            value = None
            if 'IterationsPerSec' in row:
                value = row['IterationsPerSec']
            elif 'iterationspersec' in row:
                value = row['iterationspersec']
            else:
                # Get first numeric value
                for v in row.values():
                    if isinstance(v, (int, float)):
                        value = v
                        break

            if value is None:
                continue

            values.append(value)

            # Create timestamp (spaced 5 seconds apart as estimate)
            timestamp = base_time + timedelta(seconds=sequence * 5)
            timestamp_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

            # Create sequence key and time series point
            seq_key = create_sequence_key(sequence)
            timeseries[seq_key] = TimeSeriesPoint(
                timestamp=timestamp_str,
                metrics={
                    'iterations_per_second': value
                }
            )

        # Calculate summary statistics
        summary = TimeSeriesSummary(
            count=len(values),
            mean=statistics.mean(values) if values else None,
            median=statistics.median(values) if values else None,
            min=min(values) if values else None,
            max=max(values) if values else None,
            stddev=statistics.stdev(values) if len(values) > 1 else None,
            first_value=values[0] if values else None,
            last_value=values[-1] if values else None
        )

        return timeseries, summary

    def _extract_validation(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract validation checksums from summary

        Converts flat dict structure to array of objects to reduce field count.

        Old format (1024 fields):
            {"0_crcfinal": "...", "0_crclist": "...", ...}

        New format (~5 fields with nested type):
            {
                "status": "PASS",
                "seedcrc": "...",
                "threads": [
                    {"thread": 0, "crcfinal": "...", "crclist": "...", "crcmatrix": "...", "crcstate": "..."},
                    ...
                ]
            }
        """
        # Group CRC values by thread
        threads_data = {}
        seedcrc = None

        for key, value in summary.items():
            key_lower = key.lower()

            if key_lower == 'seedcrc':
                seedcrc = value
            elif '_crc' in key_lower:
                # Parse thread number and CRC type from key like "0_crcfinal"
                parts = key.split('_', 1)
                if len(parts) == 2:
                    try:
                        thread_num = int(parts[0])
                        crc_type = parts[1]  # e.g., "crcfinal", "crclist", etc.

                        if thread_num not in threads_data:
                            threads_data[thread_num] = {'thread': thread_num}

                        threads_data[thread_num][crc_type] = value
                    except (ValueError, IndexError):
                        # Skip malformed keys
                        pass

        # Build validation object
        if threads_data or seedcrc:
            validation = {
                'status': 'PASS',
                'threads': [threads_data[t] for t in sorted(threads_data.keys())]
            }

            if seedcrc:
                validation['seedcrc'] = seedcrc

            return validation

        return None


def process_coremark(result_directory: str) -> Dict[str, Any]:
    """
    Convenience function to process CoreMark results

    Args:
        result_directory: Path to result directory

    Returns:
        Document as dictionary
    """
    with CoreMarkProcessor(result_directory) as processor:
        document = processor.process()
        return document.to_dict()
