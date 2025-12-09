"""
Pig Benchmark Processor

Processes Apache Pig scheduling efficiency benchmark results.

Pig produces:
- results_pig.csv - Scheduling efficiency at different thread counts
- test_results_report - PASS/FAIL status
- version - Test wrapper version
"""

import statistics
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime, timedelta
import logging

from .base_processor import BaseProcessor
from ..schema import Run, TimeSeriesPoint, TimeSeriesSummary, create_run_key, create_sequence_key
from ..utils.parser_utils import (
    parse_version_file,
    read_file_content
)

logger = logging.getLogger(__name__)


class PigProcessor(BaseProcessor):
    """Processor for Pig scheduling efficiency benchmark results"""

    def get_test_name(self) -> str:
        return "pig"

    def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Pig runs into object-based structure

        Single run with timeseries showing scheduling efficiency at different thread counts.

        Returns:
            {
                "run_0": {
                    "run_number": 0,
                    "status": "PASS",
                    "metrics": {
                        "average_sched_eff": 1.12,
                        "max_sched_eff": 4.00,
                        "min_sched_eff": 1.00,
                        "thread_counts": [1, 32, 64, 96, 128, 160, 192, 224, 256]
                    },
                    "timeseries": {
                        "sequence_0": {"threads": 1, "sched_eff": 4.00},
                        "sequence_1": {"threads": 32, "sched_eff": 1.03},
                        ...
                    }
                }
            }
        """
        result_dir = Path(extracted_result['extracted_path'])

        # The extracted path is already the pig_DATE directory
        # Look for the results subdirectory
        results_dir = result_dir / f"results_{self.get_test_name()}_throughput-performance"

        if not results_dir.exists():
            logger.warning(f"Results directory not found: {results_dir}")
            return {}

        # Parse the CSV file
        csv_file = results_dir / "results_pig.csv"
        if not csv_file.exists():
            logger.warning(f"CSV file not found: {csv_file}")
            return {}

        thread_data = self._parse_pig_csv(csv_file)

        # Parse version
        version_file = result_dir / "version"
        version = parse_version_file(version_file) if version_file.exists() else None

        # Parse test status
        status_file = results_dir / "test_results_report"
        status = "PASS" if status_file.exists() and "Ran" in read_file_content(status_file) else "UNKNOWN"

        # Build single run with timeseries
        run_data = self._build_run_object(
            run_number=0,
            thread_data=thread_data,
            status=status,
            version=version
        )

        runs = {create_run_key(0): run_data}

        logger.info(f"Parsed 1 Pig run with {len(thread_data)} thread configurations")
        return runs

    def _parse_pig_csv(self, csv_file: Path) -> List[Dict[str, Any]]:
        """
        Parse Pig CSV file

        Format:
        #threads:sched_eff
        1:4.00
        32:1.03
        64:1.00
        ...
        """
        thread_data = []

        with open(csv_file, 'r') as f:
            for line in f:
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue

                # Parse thread:efficiency pairs
                parts = line.split(':')
                if len(parts) == 2:
                    try:
                        threads = int(parts[0])
                        sched_eff = float(parts[1])
                        thread_data.append({
                            'threads': threads,
                            'sched_eff': sched_eff
                        })
                    except ValueError as e:
                        logger.warning(f"Failed to parse line '{line}': {e}")

        return thread_data

    def _build_run_object(
        self,
        run_number: int,
        thread_data: List[Dict[str, Any]],
        status: str,
        version: str
    ) -> Run:
        """Build a Run object from pig data"""

        # Calculate aggregate metrics
        if thread_data:
            sched_effs = [d['sched_eff'] for d in thread_data]
            threads = [d['threads'] for d in thread_data]

            metrics = {
                'average_sched_eff': statistics.mean(sched_effs),
                'max_sched_eff': max(sched_effs),
                'min_sched_eff': min(sched_effs),
                'median_sched_eff': statistics.median(sched_effs),
                'thread_counts': threads,
                'num_configurations': len(thread_data)
            }

            if len(sched_effs) > 1:
                metrics['stddev_sched_eff'] = statistics.stdev(sched_effs)
        else:
            metrics = {}

        # Build timeseries
        timeseries = {}
        ts_summary = None

        if thread_data:
            # Create synthetic timestamps for each thread configuration
            base_time = datetime.now()

            for i, data in enumerate(thread_data):
                seq_key = create_sequence_key(i)
                timestamp = (base_time + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ")

                timeseries[seq_key] = TimeSeriesPoint(
                    timestamp=timestamp,
                    metrics={
                        'threads': data['threads'],
                        'sched_eff': data['sched_eff'],
                        'sequence': i
                    }
                )

            # Create summary
            ts_summary = TimeSeriesSummary(
                count=len(thread_data),
                min=metrics['min_sched_eff'],
                max=metrics['max_sched_eff'],
                mean=metrics['average_sched_eff'],
                median=metrics['median_sched_eff'],
                stddev=metrics.get('stddev_sched_eff'),
                first_value=thread_data[0]['sched_eff'],
                last_value=thread_data[-1]['sched_eff']
            )

        # Build configuration
        configuration = {}
        if version:
            configuration['version'] = version
        if thread_data:
            configuration['thread_configurations'] = len(thread_data)
            configuration['min_threads'] = min(d['threads'] for d in thread_data)
            configuration['max_threads'] = max(d['threads'] for d in thread_data)

        return Run(
            run_number=run_number,
            status=status,
            metrics=metrics,
            configuration=configuration,
            timeseries=timeseries if timeseries else None,
            timeseries_summary=ts_summary
        )
