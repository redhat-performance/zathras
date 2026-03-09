"""
SpecJBB processor: timestamp validation (valid, missing, invalid, empty).

Converted from post_processing/demos/demo_specjbb_timestamps.py.
"""

from pathlib import Path

from post_processing.processors.specjbb_processor import SpecJBBProcessor
from tests.post_processing.conftest import run_processor_parse

FILE_KEY = "results_specjbb_csv"
FILENAME = "results_specjbb.csv"


def _write_csv(result_dir: Path, content: str) -> Path:
    path = result_dir / FILENAME
    path.write_text(content.strip())
    return path


def test_specjbb_valid_timestamps(result_dir):
    """Valid CSV with Warehouses,Bops,Numb_JVMs,Start_Date,End_Date parses successfully."""
    csv = """Warehouses,Bops,Numb_JVMs,Start_Date,End_Date
1,1000,1,2026-02-04T00:00:00Z,2026-02-04T00:05:00Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        SpecJBBProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=False,
    )


def test_specjbb_no_timestamp_columns(result_dir):
    """Legacy colon-delimited format (Warehouses:Bops) raises ProcessorError."""
    csv = """Warehouses:Bops:Numb_JVMs
1:1000:1"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        SpecJBBProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
    )


def test_specjbb_invalid_timestamp_in_row(result_dir):
    """Malformed Start_Date in a row raises ProcessorError."""
    csv = """Warehouses,Bops,Numb_JVMs,Start_Date,End_Date
1,1000,1,not-a-date,2026-02-04T00:05:00Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        SpecJBBProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
    )


def test_specjbb_empty_timestamp_in_row(result_dir):
    """Empty Start_Date in a row raises ProcessorError."""
    csv = """Warehouses,Bops,Numb_JVMs,Start_Date,End_Date
1,1000,1,,2026-02-04T00:05:00Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        SpecJBBProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
    )
