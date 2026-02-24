"""
PyPerf (Python Performance) Benchmark Processor

Processes PyPerf results including:
- 90+ Python performance benchmarks
- Multiple runs per benchmark with time series data
- Rich metadata (Python version, compiler, CPU frequency, memory usage)
- Summary statistics (mean, median, stdev)
"""

import json
import statistics
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
import logging

from .base_processor import BaseProcessor
from ..schema import (
    Run, TimeSeriesPoint, TimeSeriesSummary, create_run_key, create_sequence_key,
    ZathrasDocument, Results, PrimaryMetric
)

logger = logging.getLogger(__name__)


class PyPerfProcessor(BaseProcessor):
    """
    Processor for PyPerf Python benchmark results.

    PyPerf creates one document per benchmark to avoid OpenSearch field limits.
    On high-core systems (256 cores), 104 benchmarks would create ~26,000 fields,
    exceeding the 1,000 field limit. By splitting into separate documents,
    each document has only ~250 fields.
    """

    def get_test_name(self) -> str:
        return "pyperf"

    def process_multiple(self) -> List[ZathrasDocument]:
        """
        Process PyPerf results into multiple documents (one per benchmark).

        This overrides the default process() method to create one document
        per benchmark instead of one document with all benchmarks.

        Returns:
            List of ZathrasDocument objects, one per benchmark
        """
        logger.info(f"Processing {self.get_test_name()} results (multi-document mode)...")

        documents = []

        try:
            # Build common sections (shared across all benchmarks)
            base_metadata = self.build_metadata()
            test_info = self.build_test_info()
            sut = self.build_system_under_test()
            test_config = self.build_test_configuration()
            runtime_info = self.build_runtime_info()

            # Parse all benchmarks
            results_obj = self.build_results()
            if not isinstance(results_obj, Results):
                logger.error(f"build_results() returned unexpected type: {type(results_obj)}")
                raise TypeError(f"Expected Results object, got {type(results_obj)}")

            runs = results_obj.runs
            if not runs:
                logger.warning("No PyPerf benchmarks found")
                return []

            # Create one document per benchmark
            for run_key, run in runs.items():
                # Create a copy of metadata with benchmark-specific test name
                benchmark_name = run.metrics.get('benchmark_name', run_key)

                # Create metadata copy for this benchmark
                from dataclasses import replace
                metadata = replace(base_metadata)
                if base_metadata.scenario_name:
                    scenario = base_metadata.scenario_name or 'pyperf'
                    metadata.scenario_name = f"{scenario}_{benchmark_name}"
                else:
                    metadata.scenario_name = f"pyperf_{benchmark_name}"

                # Create Results object with only this benchmark as run_0
                single_run_results = Results(
                    status="PASS",
                    runs={
                        "run_0": Run(
                            run_number=0,
                            status=run.status,
                            metrics=run.metrics,
                            configuration=run.configuration,
                            timeseries=run.timeseries,
                            timeseries_summary=run.timeseries_summary,
                            start_time=run.start_time,
                            end_time=run.end_time,
                            duration_seconds=run.duration_seconds,
                            validation=run.validation
                        )
                    }
                )

                # Add primary metric if available
                if 'mean_seconds' in run.metrics:
                    single_run_results.primary_metric = PrimaryMetric(
                        name='mean',
                        value=run.metrics['mean_seconds'],
                        unit='seconds'
                    )

                # Create document for this benchmark
                document = ZathrasDocument(
                    metadata=metadata,
                    test=test_info,
                    system_under_test=sut,
                    test_configuration=test_config,
                    results=single_run_results,
                    runtime_info=runtime_info
                )

                # Calculate content-based hash for this specific benchmark
                content_hash = document.calculate_content_hash()
                # Use benchmark name in document ID for readability (same pattern as other tests)
                document.metadata.document_id = f"pyperf_{benchmark_name}_{content_hash[:16]}"

                documents.append(document)

            logger.info(f"Successfully processed {len(documents)} PyPerf benchmark documents")
            return documents

        except Exception as e:
            logger.error(f"Failed to process PyPerf results: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            raise

    def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse PyPerf runs into object-based structure.

        PyPerf has 90+ benchmarks, each treated as a separate run.

        Returns:
            {
                "run_0": {  # 2to3 benchmark
                    "run_number": 0,
                    "status": "PASS",
                    "metrics": {
                        "mean_seconds": 0.25530,
                        "median_seconds": 0.25525,
                        "stdev_seconds": 0.00123
                    },
                    "timeseries": {
                        "sequence_0": {
                            "timestamp": "2025-09-18T22:10:00Z",
                            "metrics": {
                                "value_seconds": 0.2553,
                                "cpu_freq_mhz": "0-7=2300 MHz",
                                "mem_max_rss_bytes": 49152000
                            }
                        },
                        ...
                    }
                },
                ...
            }
        """
        result_dir = Path(extracted_result['extracted_path'])

        # Find the JSON file with detailed results
        json_file = self._find_json_file(result_dir)
        if not json_file:
            logger.warning(f"No PyPerf JSON file found in {result_dir}")
            return {}

        # Parse JSON
        pyperf_data = self._parse_json(json_file)
        if not pyperf_data:
            return {}

        # Convert each benchmark to a Run object
        runs = {}
        for idx, benchmark in enumerate(pyperf_data.get('benchmarks', [])):
            run_key = create_run_key(idx)
            runs[run_key] = self._build_run_object(
                run_number=idx,
                benchmark=benchmark
            )

        logger.info(f"Parsed {len(runs)} PyPerf benchmarks")
        return runs

    def _find_json_file(self, result_dir: Path) -> Optional[Path]:
        """Find the PyPerf JSON file."""
        json_files = list(result_dir.glob("pyperf_out_*.json"))
        if json_files:
            return json_files[0]
        return None

    def _parse_json(self, json_file: Path) -> Optional[Dict[str, Any]]:
        """Parse PyPerf JSON file."""
        try:
            with open(json_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to parse PyPerf JSON {json_file}: {e}")
            return None

    def _build_run_object(
        self,
        run_number: int,
        benchmark: Dict[str, Any]
    ) -> Run:
        """Convert raw benchmark data to Run dataclass object."""

        metadata = benchmark.get('metadata', {})
        benchmark_runs = benchmark.get('runs', [])
        benchmark_name = metadata.get('name', f'benchmark_{run_number}')

        # Extract summary metrics
        metrics = {
            'benchmark_name': benchmark_name,
            'description': metadata.get('description', ''),
            'loops': metadata.get('loops', 0)
        }

        # Calculate statistics from run values
        all_values = []
        for run in benchmark_runs:
            values = run.get('values', [])
            if values:
                all_values.extend(values)

        if all_values:
            metrics['mean_seconds'] = statistics.mean(all_values)
            metrics['median_seconds'] = statistics.median(all_values)
            if len(all_values) > 1:
                metrics['stdev_seconds'] = statistics.stdev(all_values)
            metrics['min_seconds'] = min(all_values)
            metrics['max_seconds'] = max(all_values)
            metrics['num_samples'] = len(all_values)

        # Build time series from individual runs
        timeseries = {}
        sequence = 0

        for run in benchmark_runs:
            run_metadata = run.get('metadata', {})
            values = run.get('values', [])

            # Get timestamp from run metadata
            timestamp = run_metadata.get('date', '')
            if timestamp:
                try:
                    # Parse: "2025-09-18 22:10:00.123456"
                    dt = datetime.strptime(timestamp[:19], "%Y-%m-%d %H:%M:%S")
                    timestamp = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

            # Store each value from the run as a separate time series point
            for value in values:
                seq_key = create_sequence_key(sequence)

                ts_metrics = {
                    'value_seconds': value
                }

                # Add run-specific metadata
                if 'cpu_freq' in run_metadata:
                    ts_metrics['cpu_freq'] = run_metadata['cpu_freq']
                if 'mem_max_rss' in run_metadata:
                    ts_metrics['mem_max_rss_bytes'] = run_metadata['mem_max_rss']
                if 'duration' in run_metadata:
                    ts_metrics['run_duration_seconds'] = run_metadata['duration']

                timeseries[seq_key] = TimeSeriesPoint(
                    timestamp=timestamp,
                    metrics=ts_metrics
                )

                sequence += 1

        # Build configuration
        config = {
            'python_version': metadata.get('python_version', ''),
            'python_implementation': metadata.get('python_implementation', ''),
            'python_compiler': metadata.get('python_compiler', ''),
            'python_executable': metadata.get('python_executable', ''),
            'timer': metadata.get('timer', '')
        }

        # Add tags if present
        if 'tags' in metadata and metadata['tags']:
            config['tags'] = metadata['tags']

        # Calculate time series summary
        ts_summary = None
        if all_values:
            ts_summary = TimeSeriesSummary(
                count=len(all_values),
                mean=statistics.mean(all_values),
                median=statistics.median(all_values),
                min=min(all_values),
                max=max(all_values),
                stddev=statistics.stdev(all_values) if len(all_values) > 1 else None
            )

        return Run(
            run_number=run_number,
            status="PASS",  # PyPerf doesn't provide explicit pass/fail
            metrics=metrics,
            configuration=config,
            timeseries=timeseries if timeseries else None,
            timeseries_summary=ts_summary
        )
