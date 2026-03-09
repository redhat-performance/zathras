"""
CoreMark Pro processor: timestamp validation (valid, missing, invalid, empty).

Converted from post_processing/demos/demo_coremark_pro_timestamps.py.
"""

from pathlib import Path

from post_processing.processors.coremark_pro_processor import CoreMarkProProcessor
from tests.post_processing.conftest import run_processor_parse

FILE_KEY = "results_csv"
FILENAME = "results_coremark_pro.csv"


def _write_csv(result_dir: Path, content: str) -> Path:
    path = result_dir / FILENAME
    path.write_text(content.strip())
    return path


def test_coremark_pro_valid_timestamps(result_dir):
    """Valid CSV with Start_Date/End_Date parses successfully."""
    csv = """Test,Multi_iterations,Single_iterations,Scaling,Start_Date,End_Date
Score,100.0,50.0,2.0,2026-02-13T20:18:29Z,2026-02-13T20:19:14Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        CoreMarkProProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=False,
    )


def test_coremark_pro_no_timestamp_columns(result_dir):
    """Legacy colon-delimited format without timestamps raises ProcessorError."""
    csv = """Test:Multi_iterations:Single_iterations:Scaling
Score:100:50:2.0"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        CoreMarkProProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
    )


def test_coremark_pro_invalid_timestamp_in_row(result_dir):
    """Malformed Start_Date in a row raises ProcessorError."""
    csv = """Test,Multi_iterations,Single_iterations,Scaling,Start_Date,End_Date
Score,100.0,50.0,2.0,not-a-date,2026-02-13T20:19:14Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        CoreMarkProProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
    )


def test_coremark_pro_empty_timestamp_in_row(result_dir):
    """Empty Start_Date in a row raises ProcessorError."""
    csv = """Test,Multi_iterations,Single_iterations,Scaling,Start_Date,End_Date
Score,100.0,50.0,2.0,,2026-02-13T20:19:14Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        CoreMarkProProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
    )
