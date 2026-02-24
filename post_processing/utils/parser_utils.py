"""
Parser Utilities

Common parsing functions for various file formats found in Zathras results:
- CSV files (time series data)
- Key-value text files (run summaries, config files)
- Proc-style files (/proc/cpuinfo, /proc/meminfo)
- Test timing files
- Command files

Handles various formats and encodings gracefully.
"""

import io
import re
import csv
from typing import Dict, List, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def parse_csv_timeseries(csv_path: str, delimiter: str = ':',
                         skip_comments: bool = False) -> List[Dict[str, Any]]:
    """
    Parse time series CSV files

    Example format (results_coremark.csv, legacy):
    iteration:threads:IterationsPerSec
    1:4:193245.201809
    1:4:195999.821818
    2:4:190905.935439

    Example format (results_coremark.csv, with timestamps):
    iteration,threads,IterationsPerSec,Start_Date,End_Date
    1,4,119358.448340,2026-02-04T00:13:05Z,2026-02-04T00:13:39Z

    Args:
        csv_path: Path to CSV file
        delimiter: Column delimiter (default ':')
        skip_comments: If True, skip lines that start with '#' before the header (default False)

    Returns:
        List of dicts with parsed data:
        [
            {"iteration": 1, "threads": 4, "IterationsPerSec": 193245.201809},
            ...
        ]
    """
    if not Path(csv_path).exists():
        logger.warning(f"CSV file not found: {csv_path}")
        return []

    try:
        data = []
        if skip_comments:
            with open(csv_path, 'r') as f:
                non_comment_lines = [
                    line for line in f
                    if line.strip() and not line.strip().startswith('#')
                ]
            if not non_comment_lines:
                return []
            reader = csv.DictReader(
                io.StringIO(''.join(non_comment_lines)),
                delimiter=delimiter
            )
        else:
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                for row in reader:
                    parsed_row = {}
                    for key, value in row.items():
                        parsed_row[key] = _parse_numeric_value(value)
                    data.append(parsed_row)
            logger.debug(f"Parsed {len(data)} rows from {csv_path}")
            return data

        for row in reader:
            # Convert numeric strings to numbers (dates etc. remain as strings)
            parsed_row = {}
            for key, value in row.items():
                parsed_row[key] = _parse_numeric_value(value)
            data.append(parsed_row)

        logger.debug(f"Parsed {len(data)} rows from {csv_path}")
        return data

    except Exception as e:
        logger.error(f"Failed to parse CSV {csv_path}: {str(e)}")
        return []


def parse_key_value_text(file_path: str, separator: str = ':') -> Dict[str, Any]:
    """
    Parse key-value text files (run summaries, config files)

    Example format:
    CoreMark Size    : 666
    Total time (secs): 22.449000
    Iterations/Sec   : 195999.821818

    Args:
        file_path: Path to text file
        separator: Key-value separator (default ':')

    Returns:
        Dict of parsed key-value pairs with numeric conversion
    """
    if not Path(file_path).exists():
        logger.warning(f"File not found: {file_path}")
        return {}

    try:
        data = {}
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or separator not in line:
                    continue

                key, value = line.split(separator, 1)
                key = key.strip()
                value = value.strip()

                # Clean up key (remove extra spaces, convert to snake_case)
                clean_key = _clean_key_name(key)

                # Try to parse value
                data[clean_key] = _parse_numeric_value(value)

        logger.debug(f"Parsed {len(data)} key-value pairs from {file_path}")
        return data

    except Exception as e:
        logger.error(f"Failed to parse key-value file {file_path}: {str(e)}")
        return {}


def parse_proc_file(file_path: str) -> Dict[str, str]:
    """
    Parse /proc/* style files

    Example (proc_cpuinfo.out):
    processor  : 0
    vendor_id  : GenuineIntel
    cpu family : 6
    model      : 85

    Args:
        file_path: Path to proc file

    Returns:
        Dict of parsed values (keeps as strings for flexibility)
    """
    if not Path(file_path).exists():
        logger.warning(f"Proc file not found: {file_path}")
        return {}

    try:
        data = {}
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or ':' not in line:
                    continue

                key, value = line.split(':', 1)
                key = key.strip().replace(' ', '_').lower()
                value = value.strip()

                # Handle multiple values for same key (like in cpuinfo)
                if key in data:
                    # Convert to list if not already
                    if not isinstance(data[key], list):
                        data[key] = [data[key]]
                    data[key].append(value)
                else:
                    data[key] = value

        return data

    except Exception as e:
        logger.error(f"Failed to parse proc file {file_path}: {str(e)}")
        return {}


def parse_test_times(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse test_times file

    Example format:
    test: streams execution time 2
    test: coremark execution time 204
    test: pig execution time 519

    Args:
        file_path: Path to test_times file

    Returns:
        List of dicts:
        [
            {"test": "streams", "execution_time_seconds": 2},
            {"test": "coremark", "execution_time_seconds": 204},
            ...
        ]
    """
    if not Path(file_path).exists():
        logger.warning(f"Test times file not found: {file_path}")
        return []

    try:
        data = []
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line.startswith('test:'):
                    continue

                # Parse: "test: coremark execution time 204"
                match = re.match(r'test:\s+(\w+)\s+execution time\s+(\d+)', line)
                if match:
                    test_name = match.group(1)
                    exec_time = int(match.group(2))
                    data.append({
                        "test": test_name,
                        "execution_time_seconds": exec_time
                    })

        return data

    except Exception as e:
        logger.error(f"Failed to parse test_times {file_path}: {str(e)}")
        return []


def parse_command_file(file_path: str) -> Dict[str, Any]:
    """
    Parse {test}.cmd command file

    Example format (coremark.cmd):
    #!/bin/bash
    //root/workloads/coremark-wrapper-2.0/coremark/coremark_run --run_user root --iterations 5

    Args:
        file_path: Path to .cmd file

    Returns:
        {
            "shebang": "#!/bin/bash",
            "command": "//root/workloads/...",
            "arguments": {...}
        }
    """
    if not Path(file_path).exists():
        logger.warning(f"Command file not found: {file_path}")
        return {}

    try:
        with open(file_path, 'r') as f:
            lines = [line.strip() for line in f if line.strip()]

        data = {}

        if lines and lines[0].startswith('#!'):
            data['shebang'] = lines[0]
            command_line = lines[1] if len(lines) > 1 else ""
        else:
            command_line = lines[0] if lines else ""

        data['command'] = command_line

        # Parse arguments
        args = _parse_command_arguments(command_line)
        if args:
            data['arguments'] = args

        return data

    except Exception as e:
        logger.error(f"Failed to parse command file {file_path}: {str(e)}")
        return {}


def parse_simple_yaml(file_path: str) -> Dict[str, Any]:
    """
    Parse simple YAML files (for files that don't need full YAML parser)

    Note: For complex YAML, use the yaml library instead.
    This is for simple key: value files.

    Args:
        file_path: Path to YAML file

    Returns:
        Dict of parsed values
    """
    return parse_key_value_text(file_path, separator=':')


def read_file_lines(file_path: str, strip: bool = True) -> List[str]:
    """
    Read file and return list of lines

    Args:
        file_path: Path to file
        strip: Whether to strip whitespace from lines

    Returns:
        List of lines
    """
    if not Path(file_path).exists():
        return []

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            if strip:
                lines = [line.strip() for line in lines]
            return lines
    except Exception as e:
        logger.error(f"Failed to read file {file_path}: {str(e)}")
        return []


def read_file_content(file_path: str) -> str:
    """
    Read entire file content as string

    Args:
        file_path: Path to file

    Returns:
        File content as string
    """
    if not Path(file_path).exists():
        return ""

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to read file {file_path}: {str(e)}")
        return ""


def parse_status_file(file_path: str) -> str:
    """
    Parse simple status files (test_results_report, etc.)

    Example content: "Ran" or "PASS" or "FAIL"

    Args:
        file_path: Path to status file

    Returns:
        Status string (uppercase)
    """
    content = read_file_content(file_path).strip().upper()

    # Map common status values
    if content in ['RAN', 'PASS', 'PASSED', 'SUCCESS']:
        return 'PASS'
    elif content in ['FAIL', 'FAILED', 'ERROR']:
        return 'FAIL'
    else:
        return content if content else 'UNKNOWN'


# Helper functions

def _parse_numeric_value(value: str) -> Any:
    """Try to convert string to int or float, otherwise return string"""
    if not isinstance(value, str):
        return value

    value = value.strip()

    # Try int
    try:
        if '.' not in value:
            return int(value)
    except ValueError:
        pass

    # Try float
    try:
        return float(value)
    except ValueError:
        pass

    # Return as string
    return value


def _clean_key_name(key: str) -> str:
    """
    Clean up key name for use in dict

    Examples:
        "CoreMark Size" -> "coremark_size"
        "Total time (secs)" -> "total_time_secs"
        "Iterations/Sec" -> "iterations_per_sec"
    """
    # Remove parentheses content
    key = re.sub(r'\([^)]*\)', '', key)

    # Replace / with _per_
    key = key.replace('/', '_per_')

    # Replace spaces and special chars with underscore
    key = re.sub(r'[^\w]+', '_', key)

    # Convert to lowercase
    key = key.lower()

    # Remove leading/trailing underscores
    key = key.strip('_')

    # Collapse multiple underscores
    key = re.sub(r'_+', '_', key)

    return key


def _parse_command_arguments(command: str) -> Dict[str, str]:
    """
    Parse command line arguments

    Example:
        "command --arg1 value1 --arg2 value2"
        -> {"arg1": "value1", "arg2": "value2"}
    """
    args = {}

    # Split on spaces but preserve quoted strings
    parts = re.findall(r'--(\w+)\s+([^\s-]+)', command)

    for arg_name, arg_value in parts:
        args[arg_name] = arg_value.strip('"\'')

    return args


def parse_meminfo(file_path: str) -> Dict[str, int]:
    """
    Parse proc_meminfo.out file

    Example:
    MemTotal:       16328328 kB
    MemFree:        13445772 kB

    Args:
        file_path: Path to meminfo file

    Returns:
        Dict with memory values in KB
    """
    data = {}

    if not Path(file_path).exists():
        return data

    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if ':' not in line:
                    continue

                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()

                # Extract numeric value (remove " kB", etc.)
                match = re.match(r'(\d+)', value)
                if match:
                    data[key] = int(match.group(1))

        return data

    except Exception as e:
        logger.error(f"Failed to parse meminfo {file_path}: {str(e)}")
        return {}


def parse_version_file(file_path: str) -> str:
    """
    Parse version file

    Example content: "commit: v1.01"

    Returns just the version string: "v1.01"
    """
    content = read_file_content(file_path).strip()

    # Extract version after "commit:"
    match = re.search(r'commit:\s*(\S+)', content)
    if match:
        return match.group(1)

    return content
