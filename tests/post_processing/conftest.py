"""
Shared fixtures and helpers for post_processing processor tests.

Run from repo root (with project venv activated): PYTHONPATH=. pytest tests/post_processing/ -v
"""

from pathlib import Path
from typing import Optional

import pytest

from post_processing.processors.base_processor import ProcessorError


@pytest.fixture
def result_dir(tmp_path):
    """A temporary directory that exists, suitable as processor result_directory."""
    return tmp_path


def run_processor_parse(
    processor_class,
    result_dir_path: Path,
    files: dict,
    expect_error: bool,
    extracted_extra: Optional[dict] = None,
):
    """
    Run processor.parse_runs(extracted_result) and assert success or ProcessorError.

    - result_dir_path: path to an existing directory (processor __init__ requires it).
    - files: dict for extracted_result["files"] (e.g. {"results_csv": str(path)}).
    - expect_error: if True, assert ProcessorError is raised; else assert runs returned.
    - extracted_extra: optional dict merged into extracted_result (e.g. {"extracted_path": str(path)}).
    """
    extracted = {"files": files}
    if extracted_extra:
        extracted.update(extracted_extra)
    processor = processor_class(str(result_dir_path))
    if expect_error:
        with pytest.raises(ProcessorError):
            processor.parse_runs(extracted)
    else:
        runs = processor.parse_runs(extracted)
        assert isinstance(runs, dict)
        assert len(runs) >= 1
