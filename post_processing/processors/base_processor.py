"""
Base Processor

Abstract base class for all test result processors.
Provides common functionality for:
- Extracting SUT metadata
- Extracting test configuration
- Building complete documents
- Validation

Each test-specific processor only needs to implement parse_runs()
"""

import yaml
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import logging

from ..schema import (
    ZathrasDocument,
    Metadata,
    TestInfo,
    SystemUnderTest,
    HardwareInfo,
    CPUInfo,
    MemoryInfo,
    OperatingSystemInfo,
    ConfigurationInfo,
    TestConfiguration,
    Results,
    PrimaryMetric,
    StatisticalSummary,
    RuntimeInfo
)
from ..utils.archive_handler import ArchiveHandler
from ..utils.metadata_extractor import MetadataExtractor
from ..utils.parser_utils import (
    parse_command_file,
    parse_status_file
)

logger = logging.getLogger(__name__)


class ProcessorError(Exception):
    """Raised when processor encounters an error"""
    pass


class BaseProcessor(ABC):
    """
    Abstract base class for test result processors

    Subclasses must implement:
    - parse_runs() - Parse test-specific run data
    """

    def __init__(self, result_directory: str):
        """
        Initialize processor with result directory

        Args:
            result_directory: Path to Zathras result directory
                             (e.g., quick_sample_data/rhel/local/localhost_0/)
        """
        self.result_dir = Path(result_directory)

        if not self.result_dir.exists():
            raise ProcessorError(f"Result directory not found: {result_directory}")

        self.archive_handler = ArchiveHandler()
        self.extracted_data = {}

        logger.info(f"Initialized processor for: {result_directory}")

    @abstractmethod
    def parse_runs(self, extracted_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse test-specific run data

        Must be implemented by subclass.

        Args:
            extracted_result: Dict from archive_handler.extract_result_archive()

        Returns:
            Object-based runs structure:
            {
                "run_1": {
                    "run_number": 1,
                    "status": "PASS",
                    "metrics": {...},
                    "timeseries": {...}
                },
                "run_2": {...}
            }
        """
        pass

    @abstractmethod
    def get_test_name(self) -> str:
        """Return the test name (e.g., 'coremark', 'fio')"""
        pass

    def process(self) -> ZathrasDocument:
        """
        Main processing method - builds complete document

        Returns:
            Complete ZathrasDocument
        """
        logger.info(f"Processing {self.get_test_name()} results...")

        try:
            # Build document sections
            metadata = self.build_metadata()
            test_info = self.build_test_info()
            sut = self.build_system_under_test()
            test_config = self.build_test_configuration()
            results = self.build_results()
            runtime_info = self.build_runtime_info()

            # Create document with temporary ID
            document = ZathrasDocument(
                metadata=metadata,
                test=test_info,
                system_under_test=sut,
                test_configuration=test_config,
                results=results,
                runtime_info=runtime_info
            )

            # Calculate content-based hash for duplicate detection
            # This hash excludes processing_timestamp, so identical test results
            # will always generate the same hash, preventing duplicates in OpenSearch
            content_hash = document.calculate_content_hash()

            # Update document_id with content hash
            # Use first 16 chars of hash for readability, full hash for uniqueness
            test_name = document.test.name
            document.metadata.document_id = f"{test_name}_{content_hash[:16]}"

            logger.debug(f"Document ID: {document.metadata.document_id} (content hash: {content_hash})")

            # Validate
            is_valid, errors = document.validate()
            if not is_valid:
                logger.warning(f"Document validation errors: {errors}")

            logger.info(f"Successfully processed {self.get_test_name()} results")
            return document

        except Exception as e:
            logger.error(f"Failed to process results: {str(e)}")
            raise ProcessorError(f"Processing failed: {str(e)}") from e
        finally:
            # Cleanup temp files
            self.archive_handler.cleanup()

    def build_metadata(self) -> Metadata:
        """Build metadata section"""
        test_name = self.get_test_name()
        system_name = self.result_dir.name
        processing_time = datetime.utcnow()

        # Try to extract actual test execution timestamp
        test_timestamp_str = self._extract_test_timestamp()

        # Generate document ID: {test}_{system}_{timestamp}
        doc_id = f"{test_name}_{system_name}_{processing_time.strftime('%Y%m%d_%H%M%S')}"

        # Parse directory structure for source metadata
        # Expected structure: .../scenario_name/os_vendor/cloud_provider/instance_identifier/
        # Example: production_data/az_rhel_10_ga/rhel/azure/Standard_D8ds_v6_1/
        source_metadata = self._parse_directory_structure()

        return Metadata(
            document_id=doc_id,
            document_type="zathras_test_result",
            zathras_version="1.0",
            test_timestamp=test_timestamp_str,
            processing_timestamp=processing_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            collection_timestamp=test_timestamp_str,  # Backward compatibility
            os_vendor=source_metadata.get("os_vendor"),
            cloud_provider=source_metadata.get("cloud_provider"),
            instance_type=source_metadata.get("instance_type"),
            iteration=source_metadata.get("iteration"),
            scenario_name=source_metadata.get("scenario_name")
        )

    def build_test_info(self) -> TestInfo:
        """Build test information section"""
        test_name = self.get_test_name()

        # Try to get version from test_info file
        test_info_file = self.result_dir / "test_info"
        version = None

        if test_info_file.exists():
            try:
                import json
                with open(test_info_file, 'r') as f:
                    test_info_data = json.load(f)

                # Find test in test_info
                for key, test_data in test_info_data.items():
                    if test_data.get('test_name') == test_name:
                        version = test_data.get('repo_file', '').replace('.tar.gz', '')
                        break
            except Exception as e:
                logger.warning(f"Failed to parse test_info: {str(e)}")

        return TestInfo(
            name=test_name,
            version=version or "unknown",
            wrapper_version=version or "unknown"
        )

    def build_system_under_test(self) -> SystemUnderTest:
        """Build System Under Test metadata"""
        # Extract sysconfig_info.tar
        sysconfig_tar = self.result_dir / "sysconfig_info.tar"

        if not sysconfig_tar.exists():
            logger.warning("sysconfig_info.tar not found, SUT metadata will be incomplete")
            return SystemUnderTest(
                hardware=HardwareInfo(),
                operating_system=OperatingSystemInfo(),
                configuration=ConfigurationInfo()
            )

        try:
            # Extract sysconfig
            sysconfig_data = self.archive_handler.extract_sysconfig_archive(str(sysconfig_tar))
            sysconfig_dir = sysconfig_data['extracted_path']

            # Extract metadata
            extractor = MetadataExtractor(sysconfig_dir)
            metadata = extractor.extract_all_metadata()

            # Build hardware info
            hw_data = metadata.get('hardware', {})
            cpu_data = hw_data.get('cpu', {})
            mem_data = hw_data.get('memory', {})

            hardware = HardwareInfo(
                cpu=CPUInfo(**cpu_data) if cpu_data else None,
                memory=MemoryInfo(**mem_data) if mem_data else None,
                numa=hw_data.get('numa'),
                storage=hw_data.get('storage'),
                network=hw_data.get('network')
            )

            # Build OS info
            os_data = metadata.get('operating_system', {})
            os_info = OperatingSystemInfo(**os_data) if os_data else OperatingSystemInfo()

            # Build config info
            config_data = metadata.get('configuration', {})
            config_info = ConfigurationInfo(**config_data) if config_data else ConfigurationInfo()

            return SystemUnderTest(
                hardware=hardware,
                operating_system=os_info,
                configuration=config_info
            )

        except Exception as e:
            logger.error(f"Failed to extract SUT metadata: {str(e)}")
            return SystemUnderTest(
                hardware=HardwareInfo(),
                operating_system=OperatingSystemInfo(),
                configuration=ConfigurationInfo()
            )

    def build_test_configuration(self) -> TestConfiguration:
        """Build test configuration from ansible_vars.yml"""
        ansible_vars_file = self.result_dir / "ansible_vars.yml"

        if not ansible_vars_file.exists():
            logger.warning("ansible_vars.yml not found")
            return TestConfiguration()

        try:
            with open(ansible_vars_file, 'r') as f:
                ansible_vars = yaml.safe_load(f)

            config_info = ansible_vars.get('config_info', {})

            # Extract key parameters
            iterations = config_info.get('test_iterations')

            return TestConfiguration(
                iterations_requested=iterations,
                parameters=config_info
            )

        except Exception as e:
            logger.error(f"Failed to parse ansible_vars.yml: {str(e)}")
            return TestConfiguration()

    def build_results(self) -> Results:
        """
        Build results section

        This calls parse_runs() which must be implemented by subclass
        """
        test_name = self.get_test_name()

        # Find and extract result archive
        result_zip = self.result_dir / f"results_{test_name}.zip"

        if not result_zip.exists():
            raise ProcessorError(f"Result archive not found: {result_zip}")

        # Extract archive
        extracted = self.archive_handler.extract_result_archive(str(result_zip))
        self.extracted_data = extracted

        # Parse test_results_report for status
        status_file = extracted['files'].get('test_results_report')
        status = parse_status_file(status_file) if status_file else "UNKNOWN"

        # Parse runs (implemented by subclass)
        runs = self.parse_runs(extracted)

        # Calculate overall statistics
        overall_stats = self._calculate_overall_statistics(runs)

        # Determine primary metric
        primary_metric = self._extract_primary_metric(runs, overall_stats)

        # Calculate total execution time
        exec_time = self._calculate_execution_time(runs)

        return Results(
            status=status,
            execution_time_seconds=exec_time,
            total_runs=len(runs) if runs else 0,
            primary_metric=primary_metric,
            overall_statistics=overall_stats,
            runs=runs
        )

    def build_runtime_info(self) -> Optional[RuntimeInfo]:
        """Build runtime information"""
        test_name = self.get_test_name()

        # Parse command file
        cmd_file = self.result_dir / f"{test_name}.cmd"
        command = None

        if cmd_file.exists():
            cmd_data = parse_command_file(str(cmd_file))
            command = cmd_data.get('command')

        return RuntimeInfo(
            command=command,
            user="root"  # Default from Zathras
        )

    def _calculate_overall_statistics(self, runs: Dict[str, Any]) -> Optional[StatisticalSummary]:
        """Calculate statistics across all runs"""
        if not runs:
            return None

        # Collect all primary metric values from runs
        values = []
        for run_key, run_data in runs.items():
            if isinstance(run_data, dict) and 'metrics' in run_data:
                metrics = run_data['metrics']
                # Get the first numeric metric value
                for metric_val in metrics.values():
                    if isinstance(metric_val, (int, float)):
                        values.append(float(metric_val))
                        break

        if not values:
            return None

        import statistics

        return StatisticalSummary(
            mean=statistics.mean(values),
            median=statistics.median(values),
            min=min(values),
            max=max(values),
            stddev=statistics.stdev(values) if len(values) > 1 else 0.0,
            sample_count=len(values)
        )

    def _extract_primary_metric(
        self, runs: Dict[str, Any],
        overall_stats: Optional[StatisticalSummary]
    ) -> Optional[PrimaryMetric]:
        """Extract primary performance metric"""
        if not runs:
            return None

        # Get first run's first metric as primary
        first_run = list(runs.values())[0]
        if isinstance(first_run, dict) and 'metrics' in first_run:
            metrics = first_run['metrics']
            for metric_name, metric_val in metrics.items():
                if isinstance(metric_val, (int, float)):
                    # Use overall mean if available
                    value = overall_stats.mean if overall_stats else metric_val

                    # Determine unit from metric name
                    unit = self._guess_unit(metric_name)

                    return PrimaryMetric(
                        name=metric_name,
                        value=value,
                        unit=unit
                    )

        return None

    def _calculate_execution_time(self, runs: Dict[str, Any]) -> Optional[float]:
        """Calculate total execution time across all runs"""
        if not runs:
            return None

        total_time = 0.0
        for run_key, run_data in runs.items():
            if isinstance(run_data, dict) and 'duration_seconds' in run_data:
                total_time += run_data['duration_seconds']

        return total_time if total_time > 0 else None

    @staticmethod
    def _guess_unit(metric_name: str) -> str:
        """Guess unit from metric name"""
        metric_lower = metric_name.lower()

        if 'per_sec' in metric_lower or 'per_second' in metric_lower:
            return 'per_second'
        elif 'seconds' in metric_lower or 'time' in metric_lower:
            return 'seconds'
        elif 'bytes' in metric_lower or 'bandwidth' in metric_lower:
            return 'bytes/sec'
        elif 'iops' in metric_lower:
            return 'IOPS'
        else:
            return 'unit'

    def _extract_test_timestamp(self) -> Optional[str]:
        """
        Extract actual test execution timestamp from result files.

        Looks for timestamp in result directory names with format:
        {benchmark}_{YYYY.MM.DD-HH.MM.SS}

        Examples:
        - streams_2025.09.18-23.06.19
        - coremark_2025.11.06-05.09.45

        Returns ISO 8601 formatted timestamp or None if not found
        """
        import re

        test_name = self.get_test_name()

        # Check extracted data for timestamp in directory names
        if hasattr(self, 'extracted_data') and self.extracted_data:
            extracted_path = self.extracted_data.get('results', {}).get('extracted_path')
            if extracted_path:
                path_obj = Path(extracted_path)

                # Look for directories matching pattern: {test}_YYYY.MM.DD-HH.MM.SS
                for item in path_obj.iterdir():
                    if item.is_dir():
                        # Pattern: benchmark_2025.09.18-23.06.19
                        pattern = rf'{test_name}_(\d{{4}})\.(\d{{2}})\.(\d{{2}})-(\d{{2}})\.(\d{{2}})\.(\d{{2}})'
                        match = re.match(pattern, item.name)
                        if match:
                            year, month, day, hour, minute, second = match.groups()
                            try:
                                dt = datetime(
                                    int(year), int(month), int(day),
                                    int(hour), int(minute), int(second)
                                )
                                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                            except ValueError as e:
                                logger.warning(f"Invalid timestamp in directory name {item.name}: {e}")

        # Fallback: try to get timestamp from result ZIP file modification time
        result_zip = self.result_dir / f"results_{test_name}.zip"
        if result_zip.exists():
            mtime = result_zip.stat().st_mtime
            dt = datetime.fromtimestamp(mtime)
            logger.debug(f"Using ZIP file modification time as test timestamp: {dt}")
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        logger.warning("Could not extract test timestamp from results")
        return None

    def _parse_directory_structure(self) -> Dict[str, Any]:
        """
        Parse directory structure to extract source metadata.

        Expected structure: .../scenario_name/os_vendor/cloud_provider/instance_identifier/
        Examples:
          - production_data/az_rhel_10_ga/rhel/azure/Standard_D8ds_v6_1/
          - quick_sample_data/rhel/local/localhost_0/

        Returns dict with: os_vendor, cloud_provider, instance_type, iteration, scenario_name
        """
        import re

        result = {
            "os_vendor": None,
            "cloud_provider": None,
            "instance_type": None,
            "iteration": None,
            "scenario_name": None
        }

        # Get path parts relative to result directory
        parts = self.result_dir.parts

        # Need at least 3 parts: scenario/os_vendor/cloud_provider/instance
        if len(parts) < 3:
            logger.warning(f"Directory structure too short to parse: {self.result_dir}")
            return result

        # The instance identifier is the last part (e.g., Standard_D8ds_v6_1 or localhost_0)
        instance_full = parts[-1]

        # Parse iteration from instance name (e.g., Standard_D8ds_v6_1 -> iteration=1)
        # Match pattern: anything ending with _<number>
        iteration_match = re.search(r'_(\d+)$', instance_full)
        if iteration_match:
            result["iteration"] = int(iteration_match.group(1))
            # Instance type is everything before the iteration number
            result["instance_type"] = instance_full[:iteration_match.start()]
        else:
            result["instance_type"] = instance_full

        # Cloud provider is second-to-last (e.g., azure, local, aws, gcp)
        if len(parts) >= 2:
            result["cloud_provider"] = parts[-2]

        # OS vendor is third-to-last (e.g., rhel, ubuntu, fedora)
        if len(parts) >= 3:
            result["os_vendor"] = parts[-3]

        # Scenario name is fourth-to-last (e.g., az_rhel_10_ga)
        if len(parts) >= 4:
            result["scenario_name"] = parts[-4]

        logger.debug(f"Parsed directory structure: {result}")
        return result

    def cleanup(self):
        """Clean up temporary files"""
        self.archive_handler.cleanup()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup"""
        self.cleanup()
        return False
