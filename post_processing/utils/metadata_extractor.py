"""
Metadata Extractor

Extracts System Under Test (SUT) metadata from sysconfig files.
Builds object-based structure with dynamic keys for NUMA nodes, storage devices, etc.

Handles:
- JSON files (lscpu.json, lshw.json, lsmem.json)
- Proc files (proc_cpuinfo.out, proc_meminfo.out)
- System info files (dmidecode.out, uname.out, etc.)
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, Optional
import logging

from .parser_utils import (
    parse_proc_file,
    parse_meminfo,
    read_file_content,
    read_file_lines
)

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """Extracts and structures SUT metadata from sysconfig files"""

    def __init__(self, sysconfig_dir: str):
        """
        Initialize extractor with sysconfig directory

        Args:
            sysconfig_dir: Path to extracted sysconfig_info directory
        """
        self.sysconfig_dir = Path(sysconfig_dir)

        if not self.sysconfig_dir.exists():
            raise ValueError(f"Sysconfig directory not found: {sysconfig_dir}")

    def extract_all_metadata(self) -> Dict[str, Any]:
        """
        Extract all metadata

        Returns:
            {
                "hardware": {...},
                "operating_system": {...},
                "configuration": {...}
            }
        """
        return {
            "hardware": self.extract_hardware_metadata(),
            "operating_system": self.extract_os_metadata(),
            "configuration": self.extract_config_metadata()
        }

    def extract_hardware_metadata(self) -> Dict[str, Any]:
        """
        Extract hardware metadata

        Returns object-based structure:
        {
            "cpu": {...},
            "memory": {...},
            "numa": {"node_0": {}, "node_1": {}},
            "storage": {"device_0": {}, "device_1": {}},
            "network": {"interface_0": {}, "interface_1": {}}
        }
        """
        hardware = {}

        # CPU info
        hardware['cpu'] = self._extract_cpu_info()

        # Memory info
        hardware['memory'] = self._extract_memory_info()

        # NUMA info
        numa_info = self._extract_numa_info()
        if numa_info:
            hardware['numa'] = numa_info

        # Storage info
        storage_info = self._extract_storage_info()
        if storage_info:
            hardware['storage'] = storage_info

        # Network info
        network_info = self._extract_network_info()
        if network_info:
            hardware['network'] = network_info

        return hardware

    def extract_os_metadata(self) -> Dict[str, Any]:
        """
        Extract operating system metadata

        Returns:
            {
                "distribution": "rhel",
                "version": "9.3",
                "kernel_version": "5.14.0-362.el9.x86_64",
                "hostname": "server1"
            }
        """
        os_info = {}

        # Parse etc_release.out
        release_file = self.sysconfig_dir / "etc_release.out"
        if release_file.exists():
            release_data = self._parse_os_release(release_file)
            os_info.update(release_data)

        # Parse uname.out
        uname_file = self.sysconfig_dir / "uname.out"
        if uname_file.exists():
            uname_data = self._parse_uname(uname_file)
            os_info.update(uname_data)

        return os_info

    def extract_config_metadata(self) -> Dict[str, Any]:
        """
        Extract configuration metadata

        Returns:
            {
                "tuned_profile": "throughput-performance",
                "selinux_status": "enforcing",
                "transparent_hugepages": "always"
            }
        """
        config = {}

        # Parse tuned.out
        tuned_file = self.sysconfig_dir / "tuned.out"
        if tuned_file.exists():
            config['tuned_profile'] = self._extract_tuned_profile(tuned_file)

        # Parse sysctl parameters
        sysctl_file = self.sysconfig_dir / "sysctl.out"
        if sysctl_file.exists():
            sysctl_params = self._parse_sysctl(sysctl_file)
            if sysctl_params:
                config['sysctl_parameters'] = sysctl_params

        # Parse kernel command line
        cmdline_file = self.sysconfig_dir / "proc_cmdline.out"
        if cmdline_file.exists():
            cmdline = read_file_content(str(cmdline_file)).strip()
            # Parse into key-value pairs where possible
            parsed_params = self._parse_kernel_cmdline(cmdline)
            if parsed_params:
                config['kernel_parameters'] = parsed_params

        return config

    # Private extraction methods

    def _extract_cpu_info(self) -> Dict[str, Any]:
        """Extract CPU information from lscpu.json or proc_cpuinfo.out"""
        cpu_info = {}

        # Try lscpu.json first (already structured)
        lscpu_file = self.sysconfig_dir / "lscpu.json"
        if lscpu_file.exists():
            try:
                with open(lscpu_file, 'r') as f:
                    lscpu_data = json.load(f)

                # Extract from lscpu format
                if 'lscpu' in lscpu_data:
                    for item in lscpu_data['lscpu']:
                        field = item.get('field', '').replace(':', '').strip()
                        data = item.get('data', '')

                        if field == 'Architecture':
                            cpu_info['architecture'] = data
                        elif field == 'Vendor ID':
                            cpu_info['vendor'] = data
                        elif field == 'Model name':
                            cpu_info['model'] = data
                        elif field == 'CPU(s)':
                            cpu_info['cores'] = int(data) if data.isdigit() else None
                        elif field == 'Thread(s) per core':
                            cpu_info['threads_per_core'] = int(data) if data.isdigit() else None
                        elif field == 'Socket(s)':
                            if data != '-':
                                cpu_info['sockets'] = int(data) if data.isdigit() else None
                        elif field == 'NUMA node(s)':
                            cpu_info['numa_nodes'] = int(data) if data.isdigit() else None
                        elif 'L3 cache' in field or 'L3 cache' in data:
                            cpu_info['cache_l3'] = data
                        elif field == 'Flags':
                            # Convert flags to boolean object for OpenSearch optimization
                            flags_list = data.split()
                            cpu_info['flags'] = {flag: True for flag in flags_list}

            except Exception as e:
                logger.warning(f"Failed to parse lscpu.json: {str(e)}")

        # Fall back to proc_cpuinfo.out
        if not cpu_info:
            cpuinfo_file = self.sysconfig_dir / "proc_cpuinfo.out"
            if cpuinfo_file.exists():
                proc_data = parse_proc_file(str(cpuinfo_file))

                if 'vendor_id' in proc_data:
                    cpu_info['vendor'] = proc_data['vendor_id']
                if 'model_name' in proc_data:
                    cpu_info['model'] = proc_data['model_name']
                if 'cpu_cores' in proc_data:
                    cpu_info['cores'] = int(proc_data['cpu_cores'])

        return cpu_info

    def _extract_memory_info(self) -> Dict[str, Any]:
        """Extract memory information from lsmem.json or proc_meminfo.out"""
        memory_info = {}

        # Try lsmem.json first
        lsmem_file = self.sysconfig_dir / "lsmem.json"
        if lsmem_file.exists():
            try:
                with open(lsmem_file, 'r') as f:
                    lsmem_data = json.load(f)

                if 'memory' in lsmem_data:
                    for item in lsmem_data['memory']:
                        if item.get('field') == 'Total online memory':
                            size_str = item.get('data', '')
                            memory_info['total_gb'] = self._parse_memory_size(size_str)

            except Exception as e:
                logger.warning(f"Failed to parse lsmem.json: {str(e)}")

        # Try proc_meminfo.out
        meminfo_file = self.sysconfig_dir / "proc_meminfo.out"
        if meminfo_file.exists():
            meminfo_data = parse_meminfo(str(meminfo_file))

            if 'memtotal' in meminfo_data:
                memory_info['total_kb'] = meminfo_data['memtotal']
                # Convert to GB
                if 'total_gb' not in memory_info:
                    memory_info['total_gb'] = round(meminfo_data['memtotal'] / 1024 / 1024)

            if 'memavailable' in meminfo_data:
                memory_info['available_kb'] = meminfo_data['memavailable']

        return memory_info

    def _extract_numa_info(self) -> Optional[Dict[str, Any]]:
        """
        Extract NUMA information

        Returns object with node_0, node_1, etc. keys:
        {
            "node_0": {"cpus": "0-19,40-59", "memory_gb": 128},
            "node_1": {"cpus": "20-39,60-79", "memory_gb": 128}
        }
        """
        numa_nodes = {}

        numactl_file = self.sysconfig_dir / "numactl.out"
        if not numactl_file.exists():
            return None

        try:
            lines = read_file_lines(str(numactl_file))

            for line in lines:
                # Parse: "node 0 cpus: 0 1 2 3 4 5 6 7"
                cpu_match = re.match(r'node\s+(\d+)\s+cpus:\s+(.+)', line)
                if cpu_match:
                    node_num = cpu_match.group(1)
                    cpus = cpu_match.group(2).strip()
                    node_key = f"node_{node_num}"

                    if node_key not in numa_nodes:
                        numa_nodes[node_key] = {}

                    numa_nodes[node_key]['cpus'] = cpus

                # Parse: "node 0 size: 128000 MB"
                mem_match = re.match(r'node\s+(\d+)\s+size:\s+(\d+)\s+MB', line)
                if mem_match:
                    node_num = mem_match.group(1)
                    memory_mb = int(mem_match.group(2))
                    node_key = f"node_{node_num}"

                    if node_key not in numa_nodes:
                        numa_nodes[node_key] = {}

                    numa_nodes[node_key]['memory_gb'] = round(memory_mb / 1024)

        except Exception as e:
            logger.warning(f"Failed to parse numactl: {str(e)}")

        return numa_nodes if numa_nodes else None

    def _extract_storage_info(self) -> Optional[Dict[str, Any]]:
        """
        Extract storage device information

        Returns object with device_0, device_1, etc. keys
        """
        devices = {}

        # Try lsscsi
        lsscsi_file = self.sysconfig_dir / "lsscsi.out"
        if lsscsi_file.exists():
            try:
                lines = read_file_lines(str(lsscsi_file))
                device_num = 0

                for line in lines:
                    # Parse lsscsi output
                    if '/dev/' in line:
                        parts = line.split()
                        device_path = parts[-1] if parts else None

                        if device_path:
                            device_key = f"device_{device_num}"
                            devices[device_key] = {
                                "path": device_path,
                                "type": "scsi"
                            }
                            device_num += 1

            except Exception as e:
                logger.warning(f"Failed to parse lsscsi: {str(e)}")

        return devices if devices else None

    def _extract_network_info(self) -> Optional[Dict[str, Any]]:
        """
        Extract network interface information

        Returns object with interface_0, interface_1, etc. keys
        """
        # This would require parsing network-specific files
        # For now, return None - can be enhanced later
        return None

    def _parse_os_release(self, file_path: Path) -> Dict[str, str]:
        """Parse OS release file"""
        os_info = {}

        try:
            lines = read_file_lines(str(file_path))

            for line in lines:
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"')

                    if key == 'NAME':
                        # Extract distribution name
                        if 'fedora' in value.lower():
                            os_info['distribution'] = 'fedora'
                        elif 'red hat' in value.lower() or 'rhel' in value.lower():
                            os_info['distribution'] = 'rhel'
                        elif 'ubuntu' in value.lower():
                            os_info['distribution'] = 'ubuntu'
                        else:
                            os_info['distribution'] = value.lower()

                    elif key == 'VERSION_ID':
                        os_info['version'] = value

                # Also check first line format: "Fedora release 42"
                elif 'release' in line.lower():
                    match = re.match(r'(\w+)\s+release\s+([\d.]+)', line)
                    if match:
                        if 'distribution' not in os_info:
                            os_info['distribution'] = match.group(1).lower()
                        if 'version' not in os_info:
                            os_info['version'] = match.group(2)

        except Exception as e:
            logger.warning(f"Failed to parse OS release: {str(e)}")

        return os_info

    def _parse_uname(self, file_path: Path) -> Dict[str, str]:
        """Parse uname output"""
        uname_info = {}

        try:
            content = read_file_content(str(file_path)).strip()

            # Parse: "Linux hostname 5.14.0-362.el9.x86_64 ..."
            parts = content.split()

            if len(parts) >= 2:
                uname_info['hostname'] = parts[1]

            if len(parts) >= 3:
                uname_info['kernel_version'] = parts[2]

        except Exception as e:
            logger.warning(f"Failed to parse uname: {str(e)}")

        return uname_info

    def _extract_tuned_profile(self, file_path: Path) -> Optional[str]:
        """Extract active tuned profile"""
        try:
            content = read_file_content(str(file_path)).strip()

            # Parse: "Current active profile: throughput-performance"
            match = re.search(r'Current active profile:\s*(\S+)', content)
            if match:
                profile = match.group(1)
                # Return None if no profile is active
                return None if profile.lower() in ['none', 'null'] else profile

            # Check for "No current active profile"
            if 'No current active' in content or 'No active profile' in content:
                return None

            # Sometimes just the profile name on first line
            first_line = content.split('\n')[0].strip()
            if first_line and not first_line.startswith('Available profiles'):
                return first_line

        except Exception as e:
            logger.warning(f"Failed to parse tuned: {str(e)}")

        return None

    def _parse_sysctl(self, file_path: Path) -> Dict[str, str]:
        """Parse sysctl parameters (limited - can be very large)"""
        params = {}

        try:
            lines = read_file_lines(str(file_path))

            # Only extract key parameters (not all thousands)
            key_params = [
                'vm.swappiness',
                'vm.dirty_ratio',
                'net.core.somaxconn',
                'kernel.numa_balancing'
            ]

            for line in lines:
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    if key in key_params:
                        params[key] = value

        except Exception as e:
            logger.warning(f"Failed to parse sysctl: {str(e)}")

        return params

    def _parse_kernel_cmdline(self, cmdline: str) -> Dict[str, Any]:
        """
        Parse kernel command line into structured parameters

        Example:
            "console=tty0 console=hvc0 rw ostree=/path"
            -> {
                "console": ["tty0", "hvc0"],
                "rw": true,
                "ostree": "/path"
            }
        """
        params = {}

        # Split by spaces
        parts = cmdline.split()

        for part in parts:
            if '=' in part:
                key, value = part.split('=', 1)
                # Handle multiple values for same key
                if key in params:
                    # Convert to list if not already
                    if not isinstance(params[key], list):
                        params[key] = [params[key]]
                    params[key].append(value)
                else:
                    params[key] = value
            else:
                # Boolean flag (no value)
                params[part] = True

        # Keep only the most useful params (not the giant paths)
        useful_keys = [
            'console', 'rw', 'ro', 'quiet', 'splash', 'rhgb',
            'selinux', 'enforcing', 'nofb', 'nomodeset',
            'intel_iommu', 'amd_iommu', 'iommu',
            'hugepages', 'hugepagesz', 'default_hugepagesz',
            'numa', 'transparent_hugepage', 'elevator',
            'isolcpus', 'nohz', 'nohz_full', 'rcu_nocbs'
        ]

        filtered_params = {}
        for key in useful_keys:
            if key in params:
                filtered_params[key] = params[key]

        # Add count of total parameters
        filtered_params['_total_parameters'] = len(params)

        return filtered_params

    @staticmethod
    def _parse_memory_size(size_str: str) -> int:
        """
        Parse memory size string to GB

        Examples:
            "128G" -> 128
            "256000M" -> 256
            "1T" -> 1024
        """
        if not size_str:
            return 0

        size_str = size_str.strip().upper()

        # Extract number and unit
        match = re.match(r'([\d.]+)\s*([KMGT])?', size_str)
        if not match:
            return 0

        value = float(match.group(1))
        unit = match.group(2) if match.group(2) else 'M'

        # Convert to GB
        if unit == 'K':
            return round(value / 1024 / 1024)
        elif unit == 'M':
            return round(value / 1024)
        elif unit == 'G':
            return round(value)
        elif unit == 'T':
            return round(value * 1024)

        return round(value)


# Convenience function

def extract_metadata(sysconfig_dir: str) -> Dict[str, Any]:
    """
    Quick metadata extraction

    Args:
        sysconfig_dir: Path to sysconfig_info directory

    Returns:
        Complete metadata dict
    """
    extractor = MetadataExtractor(sysconfig_dir)
    return extractor.extract_all_metadata()
