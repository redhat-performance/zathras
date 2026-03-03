"""
SPEC CPU 2017 processor: timestamp validation (valid, missing, invalid, empty).

Converted from post_processing/demos/demo_speccpu_timestamps.py.
"""

from pathlib import Path

from post_processing.processors.speccpu2017_processor import SpecCPU2017Processor
from tests.post_processing.conftest import run_processor_parse

FILE_KEY = "results_csv"
FILENAME = "demo_intrate_timestamps.csv"


def _write_csv(result_dir: Path, content: str) -> Path:
    path = result_dir / FILENAME
    path.write_text(content.strip())
    return path


def test_speccpu2017_valid_timestamps(result_dir):
    """Valid CSV with Benchmarks,Base copies,Base Run Time,Base Rate,Start_Date,End_Date parses successfully."""
    csv = """Benchmarks,Base copies,Base Run Time,Base Rate,Start_Date,End_Date
500.perlbench_r,1,100.5,9.95,2026-02-26T03:21:32Z,2026-02-26T03:25:00Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        SpecCPU2017Processor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=False,
        extracted_extra={"extracted_path": str(result_dir)},
    )


def test_speccpu2017_no_timestamp_columns(result_dir):
    """Legacy format without Start_Date/End_Date raises ProcessorError."""
    csv = """Benchmark,Base # Copies,Base Run Time,Base Rate
500.perlbench_r,1,100.5,9.95"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        SpecCPU2017Processor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
        extracted_extra={"extracted_path": str(result_dir)},
    )


def test_speccpu2017_invalid_timestamp_in_row(result_dir):
    """Malformed Start_Date in a row raises ProcessorError."""
    csv = """Benchmarks,Base copies,Base Run Time,Base Rate,Start_Date,End_Date
500.perlbench_r,1,100.5,9.95,not-a-date,2026-02-26T03:25:00Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        SpecCPU2017Processor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
        extracted_extra={"extracted_path": str(result_dir)},
    )


def test_speccpu2017_empty_timestamp_in_row(result_dir):
    """Empty Start_Date in a row raises ProcessorError."""
    csv = """Benchmarks,Base copies,Base Run Time,Base Rate,Start_Date,End_Date
500.perlbench_r,1,100.5,9.95,,2026-02-26T03:25:00Z"""
    path = _write_csv(result_dir, csv)
    run_processor_parse(
        SpecCPU2017Processor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
        extracted_extra={"extracted_path": str(result_dir)},
    )
