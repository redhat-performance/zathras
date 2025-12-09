import csv
from typing import Dict, Any, Optional
from pathlib import Path
import logging

from .base_processor import BaseProcessor
from ..schema import Run, PrimaryMetric, create_run_key
from ..utils.parser_utils import (
    parse_version_file,
    read_file_content
)

logger = logging.getLogger(__name__)


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
        result_dir = Path(extracted_result['extracted_path'])

        # The extracted path should be the results_speccpu_throughput-performance_DATE directory
        # Look for CSV files in the result/ subdirectory
        result_subdir = result_dir / "result"
        if not result_subdir.exists():
            # Try without subdirectory
            result_subdir = result_dir

        intrate_csv = None
        fprate_csv = None
        intspeed_csv = None
        fpspeed_csv = None

        # Look for rate (throughput) results
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

        # Parse version
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

        Actual CSV format:
        Benchmark,"Base # Copies","Est. Base Run Time","Est. Base Rate",...
        500.perlbench_r,256,391.574217,1040.804096,1,S,...
        502.gcc_r,256,384.677073,942.33856,1,S,...

        Returns dict with suite-level and per-benchmark data.
        """
        benchmarks = {}
        rates = []

        content = read_file_content(csv_path)
        lines = content.splitlines()

        # Find the "Full Results Table" or "Selected Results Table"
        in_results_section = False
        header_row = None

        for i, line in enumerate(lines):
            line_stripped = line.strip().strip('"')

            # Look for results table section
            if "Results Table" in line_stripped:
                in_results_section = True
                continue

            # Skip empty lines
            if not line.strip():
                continue

            # Parse header row
            if in_results_section and header_row is None:
                if line.startswith("Benchmark,"):
                    header_row = i
                    # Parse using CSV reader
                    csv_reader = csv.DictReader(lines[header_row:])

                    for row in csv_reader:
                        # Skip empty rows or non-benchmark rows
                        if not row.get('Benchmark') or '"' in row.get('Benchmark', ''):
                            continue

                        benchmark_name = row['Benchmark'].strip()

                        # Extract data
                        try:
                            benchmark_data = {
                                'benchmark': benchmark_name
                            }

                            # Parse copies
                            if 'Base # Copies' in row:
                                try:
                                    benchmark_data['copies'] = int(float(row['Base # Copies']))
                                except (ValueError, TypeError):
                                    pass

                            # Parse runtime
                            if 'Est. Base Run Time' in row:
                                try:
                                    benchmark_data['base_runtime'] = float(row['Est. Base Run Time'])
                                except (ValueError, TypeError):
                                    pass

                            # Parse rate (primary metric)
                            if 'Est. Base Rate' in row:
                                try:
                                    base_rate = float(row['Est. Base Rate'])
                                    benchmark_data['base_rate'] = base_rate
                                    rates.append(base_rate)
                                except (ValueError, TypeError):
                                    pass

                            if benchmark_data.get('base_rate'):
                                benchmarks[benchmark_name] = benchmark_data

                        except Exception as e:
                            logger.debug(f"Could not parse benchmark row: {row.get('Benchmark')} - {e}")

                    break  # Done parsing this table

        if not benchmarks:
            logger.warning(f"No benchmarks found in {csv_path}")
            return {}

        # Calculate suite-level statistics
        suite_data = {
            'benchmarks': benchmarks,
            'num_benchmarks': len(benchmarks),
            'rates': rates
        }

        # Calculate overall suite score (geometric mean of benchmark rates)
        if rates:
            # SPEC score is geometric mean of rates
            from functools import reduce
            import operator
            product = reduce(operator.mul, rates, 1)
            suite_data['base_score'] = product ** (1.0 / len(rates))

            # For SPEC CPU 2017, the score IS the geometric mean of rates
            suite_data['est_spec_score'] = suite_data['base_score']

        return suite_data

    def _build_run_object(
        self,
        run_number: int,
        suite_data: Dict[str, Any],
        suite_name: str,
        status: str,
        version: Optional[str]
    ) -> Run:
        """Build a Run object for a SPEC CPU suite."""

        # Build suite-level metrics
        metrics = {
            'suite_name': suite_name,
            'num_benchmarks': suite_data.get('num_benchmarks', 0),
        }

        if 'base_score' in suite_data:
            metrics['base_score'] = suite_data['base_score']

        if 'est_spec_score' in suite_data:
            metrics['est_spec_score'] = suite_data['est_spec_score']

        # Add per-benchmark metrics
        benchmarks_dict = {}
        for bench_name, bench_data in suite_data.get('benchmarks', {}).items():
            bench_metrics = {}

            for key in ['base_score', 'base_runtime', 'base_rate', 'copies', 'threads']:
                if key in bench_data:
                    bench_metrics[key] = bench_data[key]

            benchmarks_dict[bench_name] = bench_metrics

        if benchmarks_dict:
            metrics['benchmarks'] = benchmarks_dict

        # Build configuration
        configuration = {
            'suite': suite_name,
            'num_benchmarks': suite_data.get('num_benchmarks', 0)
        }

        if version:
            configuration['version'] = version

        # Get copies from first benchmark if available
        first_bench = next(iter(suite_data.get('benchmarks', {}).values()), {})
        if 'copies' in first_bench:
            configuration['copies'] = first_bench['copies']

        return Run(
            run_number=run_number,
            status=status,
            metrics=metrics,
            configuration=configuration
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
