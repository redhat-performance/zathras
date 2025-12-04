"""
Auto HPL (High-Performance Linpack) Processor

Processes HPL benchmark results for measuring floating-point computing power.

Auto HPL produces:
- hpl-*.csv - Performance results (matrix size, block size, process grid, time, Gflops)
- auto_hpl.out - Detailed execution log
- test_results_report - PASS/FAIL status
- version - Test wrapper version
"""

from typing import Dict, Any
from pathlib import Path
import logging

from .base_processor import BaseProcessor
from ..schema import Run, create_run_key
from ..utils.parser_utils import (
    parse_version_file,
    read_file_content
)

logger = logging.getLogger(__name__)


class AutoHPLProcessor(BaseProcessor):
    """Processor for Auto HPL (High-Performance Linpack) benchmark results"""

    def get_test_name(self) -> str:
        return "auto_hpl"

    def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Auto HPL runs into object-based structure

        Single run with HPL performance metrics.

        Returns:
            {
                "run_0": {
                    "run_number": 0,
                    "status": "PASS",
                    "metrics": {
                        "gflops": 8308.6,
                        "time_seconds": 1639.91,
                        "matrix_size": 273408,
                        "block_size": 384,
                        "process_grid_p": 4,
                        "process_grid_q": 8
                    },
                    "configuration": {
                        "variant": "WR12R2R4",
                        "matrix_size_n": 273408,
                        "block_size_nb": 384,
                        "process_grid": "4x8"
                    }
                }
            }
        """
        result_dir = Path(extracted_result['extracted_path'])

        # The extracted path is already the auto_hpl_DATE directory
        # Find the CSV file (name varies: hpl-AMD_openblas-*.csv)
        csv_files = list(result_dir.glob("hpl-*.csv"))
        if not csv_files:
            logger.warning(f"No hpl-*.csv file found in {result_dir}")
            return {}

        csv_file = csv_files[0]

        # Parse the CSV file
        hpl_result = self._parse_hpl_csv(csv_file)

        if not hpl_result:
            logger.warning(f"No HPL results found in {csv_file}")
            return {}

        # Parse version
        version_file = result_dir / "version"
        version = parse_version_file(version_file) if version_file.exists() else None

        # Parse test status
        status_file = result_dir / "test_results_report"
        status = "PASS" if status_file.exists() and "Ran" in read_file_content(status_file) else "UNKNOWN"

        # Build single run
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
        Parse HPL CSV file

        Format:
        T/V:N:NB:P:Q:Time:Gflops
        WR12R2R4:273408:384:4:8:1639.91:8.3086e+03

        Where:
        - T/V: Variant (algorithm)
        - N: Matrix size
        - NB: Block size
        - P: Process grid rows
        - Q: Process grid columns
        - Time: Time in seconds
        - Gflops: Performance in gigaflops
        """
        hpl_result = {}

        with open(csv_file, 'r') as f:
            for line in f:
                line = line.strip()

                # Skip comments and header
                if not line or line.startswith('#') or line.startswith('T/V'):
                    continue

                # Parse result line
                parts = line.split(':')
                if len(parts) == 7:
                    try:
                        variant = parts[0]
                        n = int(parts[1])
                        nb = int(parts[2])
                        p = int(parts[3])
                        q = int(parts[4])
                        time_sec = float(parts[5])
                        gflops_str = parts[6]

                        # Parse Gflops (may be in scientific notation like 8.3086e+03)
                        gflops = float(gflops_str)

                        hpl_result = {
                            'variant': variant,
                            'matrix_size': n,
                            'block_size': nb,
                            'process_grid_p': p,
                            'process_grid_q': q,
                            'time_seconds': time_sec,
                            'gflops': gflops
                        }

                        # Only take first result
                        break

                    except (ValueError, IndexError) as e:
                        logger.warning(f"Failed to parse HPL result line '{line}': {e}")

        return hpl_result

    def _build_run_object(
        self,
        run_number: int,
        hpl_result: Dict[str, Any],
        status: str,
        version: str
    ) -> Run:
        """Build a Run object from HPL data"""

        # Build metrics
        metrics = {
            'gflops': hpl_result.get('gflops', 0),
            'time_seconds': hpl_result.get('time_seconds', 0),
            'matrix_size': hpl_result.get('matrix_size', 0),
            'block_size': hpl_result.get('block_size', 0),
            'process_grid_p': hpl_result.get('process_grid_p', 0),
            'process_grid_q': hpl_result.get('process_grid_q', 0),
            'total_processes': hpl_result.get('process_grid_p', 0) * hpl_result.get('process_grid_q', 0)
        }

        # Build configuration
        configuration = {
            'variant': hpl_result.get('variant', 'unknown'),
            'matrix_size_n': hpl_result.get('matrix_size', 0),
            'block_size_nb': hpl_result.get('block_size', 0),
            'process_grid': f"{hpl_result.get('process_grid_p', 0)}x{hpl_result.get('process_grid_q', 0)}"
        }

        if version:
            configuration['version'] = version

        return Run(
            run_number=run_number,
            status=status,
            metrics=metrics,
            configuration=configuration,
            timeseries=None,
            timeseries_summary=None
        )
