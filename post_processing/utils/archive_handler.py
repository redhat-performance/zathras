"""
Archive Handler Utility

Handles extraction of Zathras result archives:
- results_{test}.zip → results_{test}_.tar → test result files
- sysconfig_info.tar → system configuration files
- boot_info/initial_boot_info.tar → boot information

Manages temporary directories and cleanup.
"""

import os
import zipfile
import tarfile
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class ArchiveExtractionError(Exception):
    """Raised when archive extraction fails"""
    pass


class ArchiveHandler:
    """Handles extraction and management of Zathras result archives"""

    def __init__(self, cleanup_on_error: bool = True):
        """
        Initialize archive handler

        Args:
            cleanup_on_error: If True, clean up temp files even on error
        """
        self.cleanup_on_error = cleanup_on_error
        self.temp_dirs: List[str] = []

    def extract_result_archive(self, zip_path: str) -> Dict[str, Any]:
        """
        Extract results_{test}.zip archive

        Structure:
        results_{test}.zip
        └── results_{test}_.tar
            └── {test}_{timestamp}/
                ├── test_results_report
                ├── results_{test}.csv
                ├── run1_summary
                ├── run2_summary
                ├── version
                ├── tuned_setting
                └── ...

        Args:
            zip_path: Path to results_{test}.zip file

        Returns:
            {
                "test_name": "coremark",
                "extracted_path": "/tmp/extracted/coremark_2025.11.06-05.09.45/",
                "tar_path": "/tmp/results_coremark_.tar",
                "files": {
                    "test_results_report": "/path/to/file",
                    "results_csv": "/path/to/results_coremark.csv",
                    "run_summaries": ["/path/to/run1_summary", ...],
                    "version": "/path/to/version",
                    "tuned_setting": "/path/to/tuned_setting",
                    "all_files": [list of all files]
                }
            }
        """
        if not os.path.exists(zip_path):
            raise ArchiveExtractionError(f"ZIP file not found: {zip_path}")

        # Extract test name from filename: results_coremark.zip -> coremark
        test_name = os.path.basename(zip_path).replace('results_', '').replace('.zip', '')

        logger.info(f"Extracting result archive for test: {test_name}")

        try:
            # Create temp directory for extraction
            temp_dir = tempfile.mkdtemp(prefix=f"zathras_{test_name}_")
            self.temp_dirs.append(temp_dir)

            # Extract ZIP
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            # Find the tar file inside
            tar_files = list(Path(temp_dir).glob("results_*.tar"))
            if not tar_files:
                raise ArchiveExtractionError(f"No tar file found in {zip_path}")

            tar_path = str(tar_files[0])

            # Extract TAR
            with tarfile.open(tar_path, 'r') as tar_ref:
                tar_ref.extractall(temp_dir)

            # Find the result directory (typically {test}_{timestamp}/)
            result_dirs = [d for d in Path(temp_dir).iterdir() if d.is_dir()]
            if not result_dirs:
                raise ArchiveExtractionError("No result directory found after extraction")

            result_dir = str(result_dirs[0])

            # Catalog files
            files = self._catalog_result_files(result_dir, test_name)

            return {
                "test_name": test_name,
                "extracted_path": result_dir,
                "tar_path": tar_path,
                "temp_dir": temp_dir,
                "files": files
            }

        except Exception as e:
            if self.cleanup_on_error:
                self.cleanup()
            raise ArchiveExtractionError(f"Failed to extract {zip_path}: {str(e)}") from e

    def extract_sysconfig_archive(self, tar_path: str) -> Dict[str, Any]:
        """
        Extract sysconfig_info.tar archive

        Structure:
        sysconfig_info.tar
        └── sysconfig_info/
            ├── lscpu.json
            ├── lshw.json
            ├── lsmem.json
            ├── proc_cpuinfo.out
            ├── proc_meminfo.out
            ├── dmidecode.out
            ├── numactl.out
            └── ...

        Args:
            tar_path: Path to sysconfig_info.tar file

        Returns:
            {
                "extracted_path": "/tmp/sysconfig_info/",
                "files": {
                    "lscpu_json": "/path/to/lscpu.json",
                    "lshw_json": "/path/to/lshw.json",
                    "proc_cpuinfo": "/path/to/proc_cpuinfo.out",
                    ...
                }
            }
        """
        if not os.path.exists(tar_path):
            raise ArchiveExtractionError(f"TAR file not found: {tar_path}")

        logger.info(f"Extracting sysconfig archive: {tar_path}")

        try:
            # Create temp directory
            temp_dir = tempfile.mkdtemp(prefix="zathras_sysconfig_")
            self.temp_dirs.append(temp_dir)

            # Extract TAR
            with tarfile.open(tar_path, 'r') as tar_ref:
                tar_ref.extractall(temp_dir)

            # Find sysconfig_info directory
            sysconfig_dir = os.path.join(temp_dir, "sysconfig_info")
            if not os.path.exists(sysconfig_dir):
                # Try alternate structure
                subdirs = [d for d in Path(temp_dir).iterdir() if d.is_dir()]
                if subdirs:
                    sysconfig_dir = str(subdirs[0])
                else:
                    raise ArchiveExtractionError("sysconfig_info directory not found")

            # Catalog files
            files = self._catalog_sysconfig_files(sysconfig_dir)

            return {
                "extracted_path": sysconfig_dir,
                "temp_dir": temp_dir,
                "files": files
            }

        except Exception as e:
            if self.cleanup_on_error:
                self.cleanup()
            raise ArchiveExtractionError(f"Failed to extract {tar_path}: {str(e)}") from e

    def extract_boot_info_archive(self, tar_path: str) -> Dict[str, Any]:
        """
        Extract boot_info/initial_boot_info.tar archive

        Args:
            tar_path: Path to initial_boot_info.tar

        Returns:
            {
                "extracted_path": "/tmp/boot_info/",
                "files": {...}
            }
        """
        if not os.path.exists(tar_path):
            raise ArchiveExtractionError(f"Boot info TAR not found: {tar_path}")

        logger.info(f"Extracting boot info archive: {tar_path}")

        try:
            temp_dir = tempfile.mkdtemp(prefix="zathras_boot_")
            self.temp_dirs.append(temp_dir)

            with tarfile.open(tar_path, 'r') as tar_ref:
                tar_ref.extractall(temp_dir)

            # Find boot info directory
            boot_dirs = [d for d in Path(temp_dir).iterdir() if d.is_dir()]
            boot_dir = str(boot_dirs[0]) if boot_dirs else temp_dir

            files = {
                "all_files": [str(f) for f in Path(boot_dir).rglob('*') if f.is_file()]
            }

            return {
                "extracted_path": boot_dir,
                "temp_dir": temp_dir,
                "files": files
            }

        except Exception as e:
            if self.cleanup_on_error:
                self.cleanup()
            raise ArchiveExtractionError(f"Failed to extract boot info: {str(e)}") from e

    def _catalog_result_files(self, result_dir: str, test_name: str) -> Dict[str, Any]:
        """Catalog all files in result directory"""
        files = {}
        result_path = Path(result_dir)

        # Find key files
        files['test_results_report'] = self._find_file(result_path, 'test_results_report')
        files['results_csv'] = self._find_file(result_path, f'results_{test_name}.csv')
        files['version'] = self._find_file(result_path, 'version')
        files['tuned_setting'] = self._find_file(result_path, 'tuned_setting')

        # Find all run summary files
        files['run_summaries'] = sorted([
            str(f) for f in result_path.glob('run*_summary')
        ])

        # Find all iteration log files
        files['iteration_logs'] = sorted([
            str(f) for f in result_path.glob('run*_iter*.log')
        ])

        # List all files
        files['all_files'] = [
            str(f) for f in result_path.rglob('*') if f.is_file()
        ]

        return files

    def _catalog_sysconfig_files(self, sysconfig_dir: str) -> Dict[str, str]:
        """Catalog sysconfig files"""
        files = {}
        sysconfig_path = Path(sysconfig_dir)

        # JSON files
        files['lscpu_json'] = self._find_file(sysconfig_path, 'lscpu.json')
        files['lshw_json'] = self._find_file(sysconfig_path, 'lshw.json')
        files['lsmem_json'] = self._find_file(sysconfig_path, 'lsmem.json')

        # Proc files
        files['proc_cpuinfo'] = self._find_file(sysconfig_path, 'proc_cpuinfo.out')
        files['proc_meminfo'] = self._find_file(sysconfig_path, 'proc_meminfo.out')
        files['proc_cmdline'] = self._find_file(sysconfig_path, 'proc_cmdline.out')

        # System files
        files['dmidecode'] = self._find_file(sysconfig_path, 'dmidecode.out')
        files['numactl'] = self._find_file(sysconfig_path, 'numactl.out')
        files['uname'] = self._find_file(sysconfig_path, 'uname.out')
        files['etc_release'] = self._find_file(sysconfig_path, 'etc_release.out')
        files['tuned'] = self._find_file(sysconfig_path, 'tuned.out')
        files['sysctl'] = self._find_file(sysconfig_path, 'sysctl.out')

        # PCI/USB
        files['lspci'] = self._find_file(sysconfig_path, 'lspci.out')
        files['lsscsi'] = self._find_file(sysconfig_path, 'lsscsi.out')
        files['lsusb'] = self._find_file(sysconfig_path, 'lsusb.out')

        # All files
        files['all_files'] = [
            str(f) for f in sysconfig_path.rglob('*') if f.is_file()
        ]

        return files

    def _find_file(self, directory: Path, filename: str) -> Optional[str]:
        """Find a file in directory, return path or None"""
        matches = list(directory.glob(filename))
        return str(matches[0]) if matches else None

    def cleanup(self):
        """Clean up all temporary directories"""
        for temp_dir in self.temp_dirs:
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    logger.debug(f"Cleaned up temp directory: {temp_dir}")
                except Exception as e:
                    logger.warning(f"Failed to clean up {temp_dir}: {str(e)}")

        self.temp_dirs = []

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup"""
        self.cleanup()
        return False


# Convenience functions

def extract_result(zip_path: str, cleanup: bool = False) -> Dict[str, Any]:
    """
    Quick extraction of result archive

    Args:
        zip_path: Path to results_{test}.zip
        cleanup: If True, clean up immediately after extraction

    Returns:
        Extraction info dict
    """
    handler = ArchiveHandler()
    try:
        result = handler.extract_result_archive(zip_path)
        if cleanup:
            handler.cleanup()
        return result
    except Exception:
        handler.cleanup()
        raise


def extract_sysconfig(tar_path: str, cleanup: bool = False) -> Dict[str, Any]:
    """
    Quick extraction of sysconfig archive

    Args:
        tar_path: Path to sysconfig_info.tar
        cleanup: If True, clean up immediately

    Returns:
        Extraction info dict
    """
    handler = ArchiveHandler()
    try:
        result = handler.extract_sysconfig_archive(tar_path)
        if cleanup:
            handler.cleanup()
        return result
    except Exception:
        handler.cleanup()
        raise
