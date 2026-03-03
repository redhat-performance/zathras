"""
Auto HPL processor: timestamp validation (valid, missing, invalid, empty).

Converted from post_processing/demos/demo_autohpl_timestamps.py.
"""

from pathlib import Path

from post_processing.processors.autohpl_processor import AutoHPLProcessor
from tests.post_processing.conftest import run_processor_parse

FILE_KEY = "results_csv"
FILENAME = "results_auto_hpl.csv"


def _write_csv(result_dir: Path, content: str) -> Path:
    path = result_dir / FILENAME
    path.write_text(content.strip())
    return path


def test_autohpl_valid_timestamps(result_dir):
    """Valid CSV with T/V,N,NB,P,Q,Time,Gflops,Start_Date,End_Date parses successfully."""
    csv = """T/V,N,NB,P,Q,Time,Gflops,Start_Date,End_Date
HPL,100,64,2,2,10.5,50.0,2026-02-04T00:12:03Z,2026-02-04T00:12:33Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        AutoHPLProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=False,
    )


def test_autohpl_no_timestamp_columns(result_dir):
    """Colon-delimited format without timestamps raises ProcessorError."""
    csv = """T/V:N:NB:P:Q:Time:Gflops
HPL:100:64:2:2:10.5:50.0"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        AutoHPLProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
    )


def test_autohpl_invalid_timestamp_in_row(result_dir):
    """Malformed Start_Date in a row raises ProcessorError."""
    csv = """T/V,N,NB,P,Q,Time,Gflops,Start_Date,End_Date
HPL,100,64,2,2,10.5,50.0,not-a-date,2026-02-04T00:12:33Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        AutoHPLProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
    )


def test_autohpl_empty_timestamp_in_row(result_dir):
    """Empty Start_Date in a row raises ProcessorError."""
    csv = """T/V,N,NB,P,Q,Time,Gflops,Start_Date,End_Date
HPL,100,64,2,2,10.5,50.0,,2026-02-04T00:12:33Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        AutoHPLProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
    )
