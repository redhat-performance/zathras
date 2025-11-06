"""
SpecJBB (SPECjbb2005) Java Benchmark Processor

Processes SpecJBB results including:
- Multiple warehouse configurations (2, 4, 6, 8, 10, 12, 14, 16)
- Throughput (Bops - Business Operations per Second) for each
- Overall benchmark score
- Peak throughput identification
"""

import re
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
import logging

from .base_processor import BaseProcessor
from ..schema import Run, TimeSeriesPoint, create_run_key, create_sequence_key

logger = logging.getLogger(__name__)


class SpecJBBProcessor(BaseProcessor):
    """Processor for SpecJBB Java benchmark results."""

    def get_test_name(self) -> str:
        return "specjbb"

    def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse SpecJBB runs into object-based structure

        Returns:
            {
                "run_1": {
                    "run_number": 1,
                    "status": "PASS",
                    "metrics": {
                        "overall_score_bops": 293941,
                        "peak_warehouse_config": 8,
                        "peak_throughput_bops": 537647
                    },
                    "timeseries": {
                        "sequence_0": {  # 2 warehouses
                            "timestamp": "...",
                            "metrics": {
                                "warehouses": 2,
                                "throughput_bops": 215263
                            }
                        },
                        ...
                    }
                }
            }
        """
        result_dir = Path(extracted_result['extracted_path'])

        # The extracted_path already points to the specjbb_YYYY.MM.DD-HH.MM.SS directory
        # Parse CSV file with warehouse:throughput data
        csv_file = self._find_csv_file(result_dir)
        if not csv_file:
            logger.warning(f"No CSV file found in {result_dir}")
            return {}

        warehouse_data = self._parse_csv(csv_file)

        # Parse detailed results from .txt file for overall score
        txt_file = self._find_txt_file(result_dir)
        overall_score = None
        num_jvms = 1

        if txt_file:
            overall_score = self._extract_overall_score(txt_file)
            num_jvms = self._extract_num_jvms(csv_file)

        # Create a single run with all warehouse configurations
        runs = {}
        if warehouse_data:
            run_key = create_run_key(0)
            runs[run_key] = self._build_run_object(
                run_number=0,
                warehouse_data=warehouse_data,
                overall_score=overall_score,
                num_jvms=num_jvms
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

    def _parse_csv(self, csv_file: Path) -> List[Dict[str, Any]]:
        """
        Parse SpecJBB CSV file.

        Format:
        # ... comments ...
        Warehouses:Bops
        2:215263
        4:430742
        ...
        """
        warehouse_data = []

        try:
            with open(csv_file, 'r') as f:
                for line in f:
                    line = line.strip()

                    # Skip comments and headers
                    if line.startswith('#') or line == 'Warehouses:Bops':
                        continue

                    # Parse data lines: warehouses:throughput
                    if ':' in line:
                        parts = line.split(':')
                        if len(parts) == 2:
                            try:
                                warehouses = int(parts[0].strip())
                                throughput = int(parts[1].strip())
                                warehouse_data.append({
                                    'warehouses': warehouses,
                                    'throughput_bops': throughput
                                })
                            except ValueError:
                                continue

        except Exception as e:
            logger.warning(f"Failed to parse CSV {csv_file}: {e}")

        return warehouse_data

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

        # Build time series from warehouse configurations
        timeseries = {}
        for idx, data in enumerate(warehouse_data):
            seq_key = create_sequence_key(idx)
            timeseries[seq_key] = TimeSeriesPoint(
                timestamp=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                metrics={
                    'warehouses': data['warehouses'],
                    'throughput_bops': data['throughput_bops']
                }
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
