"""
CoreMark processor: timestamp validation (valid, missing, invalid/empty in row).

Converted from post_processing/demos/demo_coremark_timestamps.py.
"""

from pathlib import Path

from post_processing.processors.coremark_processor import CoreMarkProcessor
from tests.post_processing.conftest import run_processor_parse

FILE_KEY = "results_csv"
FILENAME = "results_coremark.csv"


def _write_csv(result_dir: Path, content: str) -> Path:
    path = result_dir / FILENAME
    path.write_text(content.strip())
    return path


def test_coremark_valid_timestamps(result_dir):
    """Valid comma-delimited CSV with iteration,threads,IterationsPerSec,Start_Date,End_Date parses successfully."""
    csv = """iteration,threads,IterationsPerSec,Start_Date,End_Date
1,4,119358.448340,2026-02-04T00:13:05Z,2026-02-04T00:13:39Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        CoreMarkProcessor,
        result_dir,
        {
            FILE_KEY: str(path),
            "run_summaries": [],
            "version": None,
            "tuned_setting": None,
        },
        expect_error=False,
    )


def test_coremark_no_timestamp_columns(result_dir):
    """Legacy format without Start_Date/End_Date raises ProcessorError."""
    csv = """iteration,threads,IterationsPerSec
1,4,119358.448340"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        CoreMarkProcessor,
        result_dir,
        {
            FILE_KEY: str(path),
            "run_summaries": [],
            "version": None,
            "tuned_setting": None,
        },
        expect_error=True,
    )


def test_coremark_empty_start_date_in_row(result_dir):
    """One row with missing Start_Date raises ProcessorError."""
    csv = """iteration,threads,IterationsPerSec,Start_Date,End_Date
1,4,119358.448340,,2026-02-04T00:13:39Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        CoreMarkProcessor,
        result_dir,
        {
            FILE_KEY: str(path),
            "run_summaries": [],
            "version": None,
            "tuned_setting": None,
        },
        expect_error=True,
    )
