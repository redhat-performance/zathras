"""
Passmark processor: timestamp validation (valid, missing, invalid, malformed).

Converted from post_processing/demos/demo_passmark_timestamps.py.
"""

from pathlib import Path

from post_processing.processors.passmark_processor import PassmarkProcessor
from tests.post_processing.conftest import run_processor_parse

FILE_KEY = "results_yml"
FILENAME = "results_all_1.yml"


def _write_yml(result_dir: Path, content: str) -> Path:
    path = result_dir / FILENAME
    path.write_text(content.strip())
    return path


def test_passmark_valid_timestamp(result_dir):
    """Valid YML with BaselineInfo.TimeStamp (14-digit YYYYMMDDHHmmss) parses successfully."""
    yml = """
BaselineInfo:
  WebDBID: -1
  TimeStamp: 20250918195935
Version:
  Major: 11
  Minor: 0
Results:
  NumTestProcesses: 8
  CPU_INTEGER_MATH: 35167.01
SystemInformation:
  OSName: Red Hat Enterprise Linux 9.6
"""
    path = _write_yml(result_dir, yml)
    run_processor_parse(
        PassmarkProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=False,
    )


def test_passmark_no_timestamp(result_dir):
    """YML without BaselineInfo.TimeStamp raises ProcessorError."""
    yml = """
BaselineInfo:
  WebDBID: -1
Version:
  Major: 11
Results:
  NumTestProcesses: 8
  CPU_INTEGER_MATH: 35167.01
"""
    path = _write_yml(result_dir, yml)
    run_processor_parse(
        PassmarkProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
    )


def test_passmark_invalid_timestamp(result_dir):
    """YML with non-14-digit TimeStamp raises ProcessorError."""
    yml = """
BaselineInfo:
  TimeStamp: not-14-digits
Version:
  Major: 11
Results:
  NumTestProcesses: 8
  CPU_INTEGER_MATH: 35167.01
"""
    path = _write_yml(result_dir, yml)
    run_processor_parse(
        PassmarkProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
    )


def test_passmark_malformed_timestamp(result_dir):
    """YML with empty TimeStamp raises ProcessorError."""
    yml = """
BaselineInfo:
  TimeStamp: ''
Version:
  Major: 11
Results:
  NumTestProcesses: 8
  CPU_INTEGER_MATH: 35167.01
"""
    path = _write_yml(result_dir, yml)
    run_processor_parse(
        PassmarkProcessor,
        result_dir,
        {FILE_KEY: str(path)},
        expect_error=True,
    )
