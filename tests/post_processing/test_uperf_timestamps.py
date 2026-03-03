"""
Uperf processor: timestamp validation (valid, missing, invalid, empty).

Converted from post_processing/demos/demo_uperf_timestamps.py.
"""

from pathlib import Path

from post_processing.processors.uperf_processor import UperfProcessor
from tests.post_processing.conftest import run_processor_parse

FILE_KEY = "results_uperf_csv"
FILENAME = "results_uperf.csv"


def _write_csv(result_dir: Path, content: str) -> Path:
    path = result_dir / FILENAME
    path.write_text(content.strip())
    return path


def test_uperf_valid_timestamps(result_dir):
    """Valid CSV with header containing Start_Date,End_Date parses successfully."""
    csv = """number_procs,Gb_Sec,trans_sec,lat_usec,test_type,packet_type,packet_size,Start_Date,End_Date
1,2.5,1000.0,50.0,stream,udp,16384,2026-02-04T00:10:00Z,2026-02-04T00:10:30Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        UperfProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=False,
    )


def test_uperf_no_timestamp_columns(result_dir):
    """CSV without Start_Date/End_Date in header raises ProcessorError."""
    csv = """number_procs,Gb_Sec,trans_sec,lat_usec,test_type,packet_type,packet_size
1,2.5,1000.0,50.0,stream,udp,16384"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        UperfProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
    )


def test_uperf_invalid_timestamp_in_row(result_dir):
    """Malformed Start_Date in a row raises ProcessorError."""
    csv = """number_procs,Gb_Sec,trans_sec,lat_usec,test_type,packet_type,packet_size,Start_Date,End_Date
1,2.5,1000.0,50.0,stream,udp,16384,not-a-date,2026-02-04T00:10:30Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        UperfProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
    )


def test_uperf_empty_timestamp_in_row(result_dir):
    """Empty Start_Date in a row raises ProcessorError."""
    csv = """number_procs,Gb_Sec,trans_sec,lat_usec,test_type,packet_type,packet_size,Start_Date,End_Date
1,2.5,1000.0,50.0,stream,udp,16384,,2026-02-04T00:10:30Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        UperfProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
    )
