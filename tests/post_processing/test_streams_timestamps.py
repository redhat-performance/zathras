"""
STREAMS processor: timestamp validation (valid, missing, invalid, empty).

Converted from post_processing/demos/demo_streams_timestamps.py.
"""

from pathlib import Path

from post_processing.processors.streams_processor import StreamsProcessor
from tests.post_processing.conftest import run_processor_parse

FILE_KEY = "results_streams_csv"
FILENAME = "results_streams.csv"


def _write_csv(result_dir: Path, content: str) -> Path:
    path = result_dir / FILENAME
    path.write_text(content.strip())
    return path


def test_streams_valid_timestamps(result_dir):
    """Valid CSV with Array sizes,...,Start_Date,End_Date and operation row parses successfully."""
    csv = """Array sizes,16384k,32768k,65536k,Start_Date,End_Date
Copy,1.0,2.0,3.0,2026-02-04T00:19:56Z,2026-02-04T00:20:00Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        StreamsProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=False,
    )


def test_streams_no_timestamp_columns(result_dir):
    """Colon-delimited format without timestamps raises ProcessorError."""
    csv = """Array sizes:16384k:32768k:65536k
Copy:1.0:2.0:3.0"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        StreamsProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
    )


def test_streams_invalid_timestamp_in_row(result_dir):
    """Malformed Start_Date in a row raises ProcessorError."""
    csv = """Array sizes,16384k,32768k,65536k,Start_Date,End_Date
Copy,1.0,2.0,3.0,not-a-date,2026-02-04T00:20:00Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        StreamsProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
    )


def test_streams_empty_timestamp_in_row(result_dir):
    """Empty Start_Date in a row raises ProcessorError."""
    csv = """Array sizes,16384k,32768k,65536k,Start_Date,End_Date
Copy,1.0,2.0,3.0,,2026-02-04T00:20:00Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        StreamsProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
    )
