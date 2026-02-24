#!/usr/bin/env python3
"""
Zathras Post-Processing Orchestrator

End-to-end pipeline for processing Zathras benchmark results and exporting
to OpenSearch and/or Horreum.

Usage:
    # Process all benchmarks in a directory and export to OpenSearch
    python -m post_processing.run_postprocessing --input /path/to/results --opensearch

    # Export to both OpenSearch and Horreum
    python -m post_processing.run_postprocessing --input /path/to/results --opensearch --horreum

    # Just create JSON files (no export)
    python -m post_processing.run_postprocessing --input /path/to/results --output-json results/

    # Use custom config
    python -m post_processing.run_postprocessing --input /path/to/results --config export_config.yml
"""

import argparse
import sys
import logging
import yaml
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime

# Import all processors
from .processors.coremark_processor import CoreMarkProcessor
from .processors.streams_processor import StreamsProcessor
from .processors.specjbb_processor import SpecJBBProcessor
from .processors.pyperf_processor import PyPerfProcessor
from .processors.coremark_pro_processor import CoreMarkProProcessor
from .processors.passmark_processor import PassmarkProcessor
from .processors.phoronix_processor import PhoronixProcessor
from .processors.uperf_processor import UperfProcessor
from .processors.pig_processor import PigProcessor
from .processors.autohpl_processor import AutoHPLProcessor
from .processors.speccpu2017_processor import SpecCPU2017Processor
from .processors.fio_processor import FioProcessor

# Import exporters
from .exporters.opensearch_exporter import OpenSearchExporter
from .exporters.timeseries_exporter import TimeSeriesExporter
from .exporters.horreum_exporter import HorreumExporter


# Color codes for terminal output
class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log levels"""

    # ANSI color codes
    COLORS = {
        'WARNING': '\033[93m',  # Yellow
        'ERROR': '\033[91m',    # Red
        'RESET': '\033[0m'      # Reset
    }

    def format(self, record):
        # Save the original levelname
        levelname = record.levelname

        # Add color to WARNING and ERROR levels
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"

        # Format the message
        result = super().format(record)

        # Restore original levelname
        record.levelname = levelname

        return result


# Configure logging with colors
handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logging.root.addHandler(handler)
logging.root.setLevel(logging.INFO)
logger = logging.getLogger(__name__)


# Processor registry - maps test names to processor classes
PROCESSOR_REGISTRY = {
    'coremark': CoreMarkProcessor,
    'streams': StreamsProcessor,
    'specjbb': SpecJBBProcessor,
    'pyperf': PyPerfProcessor,
    'coremark_pro': CoreMarkProProcessor,
    'passmark': PassmarkProcessor,
    'phoronix': PhoronixProcessor,
    'uperf': UperfProcessor,
    'pig': PigProcessor,
    'auto_hpl': AutoHPLProcessor,
    'speccpu2017': SpecCPU2017Processor,
    'fio': FioProcessor,
}


class ProcessingStats:
    """Track processing statistics"""

    def __init__(self):
        self.total = 0
        self.successful = 0
        self.failed = 0
        self.skipped = 0
        self.errors: List[Tuple[str, str]] = []
        self.processed_tests: Dict[str, int] = {}
        self.documents_created = 0
        self.documents_duplicates = 0
        self.timeseries_indexed = 0
        self.timeseries_skipped = 0
        self.opensearch_export_enabled = False
        self.start_time = datetime.now()

    def record_success(self, test_name: str):
        self.successful += 1
        self.processed_tests[test_name] = self.processed_tests.get(test_name, 0) + 1

    def record_failure(self, test_name: str, error: str):
        self.failed += 1
        self.errors.append((test_name, error))

    def record_skip(self, test_name: str, reason: str):
        self.skipped += 1
        self.errors.append((test_name, f"SKIPPED: {reason}"))

    def record_document_created(self):
        """Track when a new document is created in OpenSearch"""
        self.documents_created += 1

    def record_duplicate(self):
        """Track when a duplicate document is detected and skipped"""
        self.documents_duplicates += 1

    def record_timeseries_indexed(self, count: int):
        """Track time series points that were indexed"""
        self.timeseries_indexed += count

    def record_timeseries_skipped(self, count: int):
        """Track time series points that were skipped (due to duplicate summary)"""
        self.timeseries_skipped += count

    def get_summary(self) -> str:
        duration = (datetime.now() - self.start_time).total_seconds()

        summary = [
            "",
            "=" * 70,
            "PROCESSING SUMMARY",
            "=" * 70,
            f"Total: {self.total}",
            f"Successful: {self.successful}",
            f"Failed: {self.failed}",
            f"Skipped: {self.skipped}",
            f"Duration: {duration:.2f} seconds",
            "",
        ]

        # Show OpenSearch summary document stats (if OpenSearch export was enabled)
        if self.opensearch_export_enabled:
            total_docs = self.documents_created + self.documents_duplicates
            summary.append("OpenSearch Summary Documents:")
            summary.append(f"  Total: {total_docs}")
            summary.append(f"  Indexed: {self.documents_created}")
            summary.append(f"  Duplicates (skipped): {self.documents_duplicates}")
            summary.append("")

            # Show time series stats
            total_ts = self.timeseries_indexed + self.timeseries_skipped
            summary.append("OpenSearch Time Series Documents:")
            summary.append(f"  Total: {total_ts}")
            summary.append(f"  Indexed: {self.timeseries_indexed}")
            summary.append(f"  Duplicates (skipped): {self.timeseries_skipped}")
            summary.append("")

        if self.processed_tests:
            summary.append("Tests Processed:")
            for test_name, count in sorted(self.processed_tests.items()):
                summary.append(f"  - {test_name}: {count}")
            summary.append("")

        if self.errors:
            summary.append(f"Errors ({len(self.errors)}):")
            # Show ALL errors, not just first 10
            for test_name, error in self.errors:
                summary.append(f"  - {test_name}: {error}")
            summary.append("")

        summary.append("=" * 70)

        return "\n".join(summary)


def discover_result_directories(input_path: Path) -> List[Path]:
    """
    Discover all result directories that contain results_*.zip files.

    Args:
        input_path: Path to search (can be a directory or a specific result dir)

    Returns:
        List of directories containing benchmark results
    """
    result_dirs = []

    if input_path.is_file():
        logger.error(f"Input path is a file, not a directory: {input_path}")
        return []

    # Check if input_path itself contains results
    if list(input_path.glob("results_*.zip")):
        result_dirs.append(input_path)
        logger.info(f"Found results in: {input_path}")
        return result_dirs

    # Search recursively for directories containing results_*.zip
    for path in input_path.rglob("results_*.zip"):
        result_dir = path.parent
        if result_dir not in result_dirs:
            result_dirs.append(result_dir)
            logger.info(f"Found results in: {result_dir}")

    return sorted(result_dirs)


def detect_test_type(result_file: Path) -> Optional[str]:
    """
    Detect test type from results_*.zip filename.

    Args:
        result_file: Path to results_*.zip file

    Returns:
        Test type name (e.g., 'coremark', 'streams') or None if unknown
    """
    # Extract test name from filename: results_<test>.zip
    filename = result_file.name
    if not filename.startswith("results_") or not filename.endswith(".zip"):
        return None

    test_name = filename[8:-4]  # Remove "results_" prefix and ".zip" suffix

    if test_name in PROCESSOR_REGISTRY:
        return test_name

    logger.warning(f"Unknown test type: {test_name}")
    return None


def load_config(config_path: Optional[Path]) -> Dict[str, Any]:
    """Load configuration from YAML file"""
    if not config_path or not config_path.exists():
        return {}

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        logger.info(f"Loaded config from: {config_path}")
        return config or {}
    except Exception as e:
        logger.error(f"Failed to load config from {config_path}: {e}")
        return {}


def process_result_directory(
    result_dir: Path,
    config: Dict[str, Any],
    export_opensearch: bool = False,
    export_horreum: bool = False,
    output_json_dir: Optional[Path] = None,
    stats: Optional[ProcessingStats] = None
) -> Dict[str, Any]:
    """
    Process all benchmarks in a result directory.

    Args:
        result_dir: Directory containing results_*.zip files
        config: Configuration dictionary
        export_opensearch: Export to OpenSearch
        export_horreum: Export to Horreum
        output_json_dir: Directory to write JSON files
        stats: ProcessingStats object for tracking

    Returns:
        Dictionary with processing results
    """
    if stats is None:
        stats = ProcessingStats()

    # Initialize exporters if needed
    opensearch_summary_exporter = None
    opensearch_ts_exporter = None
    horreum_exporter = None

    if export_opensearch:
        try:
            opensearch_config = config.get('opensearch', {})
            opensearch_summary_exporter = OpenSearchExporter(
                url=opensearch_config.get('url', 'http://localhost:9200'),
                index=opensearch_config.get('summary_index', 'zathras-results'),
                username=opensearch_config.get('username'),
                password=opensearch_config.get('password'),
                verify_ssl=opensearch_config.get('verify_ssl', True)
            )

            opensearch_ts_exporter = TimeSeriesExporter(
                url=opensearch_config.get('url', 'http://localhost:9200'),
                index=opensearch_config.get('timeseries_index', 'zathras-timeseries'),
                username=opensearch_config.get('username'),
                password=opensearch_config.get('password'),
                verify_ssl=opensearch_config.get('verify_ssl', True)
            )

            logger.info(f"OpenSearch exporters initialized: {opensearch_config.get('url')}")
        except Exception as e:
            logger.error(f"Failed to initialize OpenSearch exporters: {e}")
            export_opensearch = False

    if export_horreum:
        try:
            horreum_config = config.get('horreum', {})
            horreum_exporter = HorreumExporter(
                url=horreum_config.get('url', 'http://localhost:8080'),
                username=horreum_config.get('username'),
                password=horreum_config.get('password')
            )
            logger.info(f"Horreum exporter initialized: {horreum_config.get('url')}")
        except Exception as e:
            logger.error(f"Failed to initialize Horreum exporter: {e}")
            export_horreum = False

    # Discover all result files
    result_files = sorted(result_dir.glob("results_*.zip"))

    if not result_files:
        logger.warning(f"No results_*.zip files found in {result_dir}")
        return {'processed': 0, 'errors': []}

    logger.info(f"Found {len(result_files)} result file(s) in {result_dir}")

    results = []

    # Process each result file
    for result_file in result_files:
        stats.total += 1
        test_name = detect_test_type(result_file)

        if not test_name:
            stats.record_skip(result_file.name, "Unknown test type")
            continue

        logger.info(f"[{stats.total}/{len(result_files)}] Processing {test_name}: {result_file.name}")

        try:
            # Get processor class
            processor_class = PROCESSOR_REGISTRY[test_name]

            # Process the results
            processor = processor_class(result_dir)

            # Check if processor supports multi-document mode (e.g., PyPerf)
            if hasattr(processor, 'process_multiple'):
                documents = processor.process_multiple()
                logger.info(f"  Parsed {test_name}: {len(documents)} documents")
            else:
                documents = [processor.process()]
                logger.info(f"  Parsed {test_name}: {documents[0].metadata.document_id}")

            # Export to JSON files if requested
            if output_json_dir:
                output_json_dir.mkdir(parents=True, exist_ok=True)
                for document in documents:
                    json_file = output_json_dir / f"{document.metadata.document_id}.json"
                    with open(json_file, 'w') as f:
                        f.write(document.to_json())
                if len(documents) == 1:
                    logger.info(f"  Wrote JSON: {json_file.name}")
                else:
                    logger.info(f"  Wrote {len(documents)} JSON files")

            # Track export failures
            export_failed = False
            export_error = None

            # Export each document to OpenSearch (two-index architecture)
            for document in documents:
                if export_opensearch and opensearch_summary_exporter and opensearch_ts_exporter:
                    try:
                        # Export summary (without raw time series)
                        summary_dict = document.to_dict_summary_only()
                        doc_id = document.metadata.document_id

                        # Try to create document (will fail if duplicate exists)
                        result = opensearch_summary_exporter.create_document(summary_dict, doc_id=doc_id)
                        operation = result['result']  # 'created' or 'duplicate'

                        # Track whether this was a new document or duplicate
                        if operation == 'created':
                            stats.record_document_created()
                            if len(documents) == 1:
                                logger.info(f"  Created in OpenSearch (summary): {doc_id}")

                            # Export time series only if summary was created (not duplicate)
                            ts_count = sum(
                                len(run.timeseries) for run in document.results.runs.values()
                                if run.timeseries
                            )

                            if ts_count > 0:
                                ts_result = opensearch_ts_exporter.export_from_zathras_document(
                                    document, batch_size=500
                                )
                                stats.record_timeseries_indexed(ts_result['successful'])
                                if len(documents) == 1:
                                    ts_msg = (
                                        f"  Exported to OpenSearch (timeseries): "
                                        f"{ts_result['successful']}/{ts_result['total']} points"
                                    )
                                    logger.info(ts_msg)

                                if ts_result['failed'] > 0:
                                    logger.warning(f"     Failed: {ts_result['failed']} time series points")

                        elif operation == 'duplicate':
                            stats.record_duplicate()

                            # Count time series that would have been indexed (but skipped due to duplicate)
                            ts_count = sum(
                                len(run.timeseries) for run in document.results.runs.values()
                                if run.timeseries
                            )
                            if ts_count > 0:
                                stats.record_timeseries_skipped(ts_count)

                            if len(documents) == 1:
                                logger.warning(f"  Duplicate detected, skipped: {doc_id}")

                    except Exception as e:
                        export_failed = True
                        export_error = f"OpenSearch export failed: {e}"
                        logger.error(f"  {export_error}")

                # Export to Horreum
                if export_horreum and horreum_exporter:
                    try:
                        run_id = horreum_exporter.export_zathras_document(document)
                        if len(documents) == 1:
                            logger.info(f"  Exported to Horreum: run {run_id}")
                    except Exception as e:
                        if not export_failed:
                            export_failed = True
                            export_error = f"Horreum export failed: {e}"
                        logger.error(f"  Horreum export failed: {e}")

            # Add summary logging for multi-document exports
            if len(documents) > 1 and export_opensearch:
                logger.info(f"  Processed {len(documents)} PyPerf benchmark documents")

            # Record success or failure
            if export_failed:
                stats.record_failure(test_name, export_error)
                results.append({
                    'test_name': test_name,
                    'status': 'failed',
                    'error': export_error
                })
            else:
                stats.record_success(test_name)
                doc_id = (
                    documents[0].metadata.document_id if len(documents) == 1
                    else f"{len(documents)} documents"
                )
                results.append({
                    'test_name': test_name,
                    'document_id': doc_id,
                    'status': 'success'
                })

        except Exception as e:
            logger.error(f"  Failed to process {test_name}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            stats.record_failure(test_name, str(e))
            results.append({
                'test_name': test_name,
                'status': 'failed',
                'error': str(e)
            })

    return {
        'directory': str(result_dir),
        'processed': len([r for r in results if r['status'] == 'success']),
        'failed': len([r for r in results if r['status'] == 'failed']),
        'results': results
    }


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Zathras Post-Processing Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all benchmarks in a directory and export to OpenSearch
  %(prog)s --input /path/to/results --opensearch

  # Export to both OpenSearch and Horreum
  %(prog)s --input /path/to/results --opensearch --horreum

  # Just create JSON files (no export)
  %(prog)s --input /path/to/results --output-json results/

  # Use custom config
  %(prog)s --input /path/to/results --config export_config.yml --opensearch
        """
    )

    parser.add_argument(
        '--input',
        type=Path,
        required=True,
        help='Input directory containing Zathras results (can contain multiple subdirectories)'
    )

    parser.add_argument(
        '--config',
        type=Path,
        help='Configuration file (YAML) with export settings'
    )

    parser.add_argument(
        '--opensearch',
        action='store_true',
        help='Export to OpenSearch (requires config with opensearch section)'
    )

    parser.add_argument(
        '--horreum',
        action='store_true',
        help='Export to Horreum (requires config with horreum section)'
    )

    parser.add_argument(
        '--output-json',
        type=Path,
        help='Directory to write JSON files'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    # Configure logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate input
    if not args.input.exists():
        logger.error(f"Input path does not exist: {args.input}")
        sys.exit(1)

    # Load configuration
    config = load_config(args.config)

    # Check if at least one export method is specified
    if not args.opensearch and not args.horreum and not args.output_json:
        logger.warning("No export method specified (--opensearch, --horreum, or --output-json)")
        logger.warning("Will process but not export data")

    # Discover result directories
    logger.info(f"Searching for results in: {args.input}")
    result_dirs = discover_result_directories(args.input)

    if not result_dirs:
        logger.error("No result directories found")
        sys.exit(1)

    logger.info(f"Found {len(result_dirs)} result directory(ies)")
    logger.info("")

    # Process all directories
    stats = ProcessingStats()
    stats.opensearch_export_enabled = args.opensearch

    for i, result_dir in enumerate(result_dirs, 1):
        logger.info(f"[{i}/{len(result_dirs)}] Processing directory: {result_dir}")
        logger.info("-" * 70)

        process_result_directory(
            result_dir=result_dir,
            config=config,
            export_opensearch=args.opensearch,
            export_horreum=args.horreum,
            output_json_dir=args.output_json,
            stats=stats
        )

        logger.info("")

    # Print summary
    print(stats.get_summary())

    # Exit with appropriate code
    if stats.failed > 0:
        sys.exit(1)
    elif stats.successful == 0:
        logger.error("No benchmarks were successfully processed")
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
