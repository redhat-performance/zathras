#!/usr/bin/env python3
#
# Azure cost tracking for a Zathras run directory.
#
# Pricing is never hard-coded in this file. Rates come from, in order:
#   1) config/azure_pricing_overrides.cfg
#   2) the run's instance_cost file (captured at start from Retail Prices)
#   3) Azure Retail Prices API
# Missing rates are recorded as unavailable; they are not guessed.
#
# Runtime hierarchy:
#   Level 1 — terraform apply end → terraform destroy end (instance_lifecycle)
#   Level 2 — Zathras create_end → terminate_start
#   Level 3 — sum of test_times (test execution only; labeled estimate)
#   Level 4 — --configured-runtime-seconds (explicit estimate)
#
# Resource inventory prefers terraform_inventory.json (terraform show -json
# snapshot taken after apply, before destroy). Ansible inference is fallback.
#
# Cost tracking is a plugin (zathras_cost_hook + cost_track role). Failures
# must not fail Terraform or the benchmark.
#

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

SECONDS_PER_HOUR = 3600.0
CURRENCY = "USD"
DEFAULT_OS_DISK_TYPE = "Premium_LRS"

_UTILS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_UTILS_DIR, "..", ".."))
if _UTILS_DIR not in sys.path:
    sys.path.insert(0, _UTILS_DIR)

try:
    from azure_instance_price import (
        lookup_vm_hourly_price,
        lookup_managed_disk_hourly_price,
        lookup_managed_disk_monthly_price,
        lookup_public_ip_hourly_price,
        monthly_to_hourly,
        HOURS_PER_MONTH,
        AzurePriceError,
    )
except ImportError:  # pragma: no cover
    lookup_vm_hourly_price = None  # type: ignore
    lookup_managed_disk_hourly_price = None  # type: ignore
    lookup_managed_disk_monthly_price = None  # type: ignore
    lookup_public_ip_hourly_price = None  # type: ignore
    monthly_to_hourly = None  # type: ignore
    HOURS_PER_MONTH = 730.0
    AzurePriceError = Exception  # type: ignore


class CostError(Exception):
    """Cost calculation could not proceed."""


@dataclass
class ResourceUsage:
    resource_id: str
    resource_type: str
    resource_name: str
    sku: str
    region: str
    quantity: float
    start_time: Optional[int]
    end_time: Optional[int]
    runtime_seconds: int
    runtime_source: str
    runtime_is_estimate: bool
    unit: str
    attribution: str = "direct"
    notes: str = ""
    billable: bool = True
    # For managed disks: size used when looking up Retail tier/GB meters.
    disk_size_gb: Optional[int] = None


@dataclass
class ResourceCost:
    usage: ResourceUsage
    hourly_rate: Optional[float]
    daily_rate: Optional[float]
    total_cost: Optional[float]
    currency: str
    pricing_source: str
    calculation: str


@dataclass
class RunCost:
    run_id: str
    start_time: Optional[int]
    end_time: Optional[int]
    runtime_seconds: int
    runtime_source: str
    status: str
    currency: str
    resources: List[ResourceCost]
    total_cost: Optional[float]
    average_cost_per_hour: Optional[float]
    estimated_24h_cost: Optional[float]
    category_totals: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


def hours_from_seconds(seconds: float) -> float:
    return float(seconds) / SECONDS_PER_HOUR


def runtime_seconds(
    start: Optional[int],
    end: Optional[int],
    *,
    missing: str = "zero",
) -> Tuple[int, str]:
    if start is None or end is None:
        if missing == "error":
            raise CostError("missing timestamps")
        return 0, "missing_timestamps"
    if end < start:
        return 0, "end_before_start"
    return int(end - start), "ok"


def parse_kv_file(path: str) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not os.path.isfile(path):
        return data
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
            elif ":" in line:
                key, val = line.split(":", 1)
            else:
                continue
            data[key.strip()] = val.strip().strip('"').strip("'")
    return data


def parse_config_info(path: str) -> Dict[str, str]:
    info: Dict[str, str] = {}
    if not os.path.isfile(path):
        return info
    in_config = False
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            if raw.startswith("config_info:"):
                in_config = True
                continue
            if in_config:
                if raw.strip() and not raw.startswith(" ") and not raw.startswith("\t"):
                    break
                match = re.match(r"\s+([A-Za-z0-9_]+):\s*(.*)$", raw)
                if not match:
                    continue
                key, val = match.group(1), match.group(2).strip()
                if val.startswith("[") and val.endswith("]"):
                    val = val[1:-1].strip()
                info[key] = val.strip('"').strip("'")
    return info


def parse_test_times(path: str) -> List[Tuple[str, int]]:
    rows: List[Tuple[str, int]] = []
    if not os.path.isfile(path):
        return rows
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            match = re.search(r"test:\s+(\S+).*execution time\s+(\d+)", raw)
            if match:
                rows.append((match.group(1), int(match.group(2))))
    return rows


def parse_cloud_disks(value: str) -> Tuple[int, str, int]:
    """burden format: count:type:size:... → (count, storage_account_type, size_gb)."""
    if not value or value in ("none", "[]"):
        return 0, "", 0
    cleaned = value.replace("'", "").replace('"', "").replace("[", "").replace("]", "")
    parts = cleaned.split(":")
    try:
        count = int(float(parts[0]))
    except (ValueError, IndexError):
        return 0, "", 0
    if count <= 0:
        return 0, "", 0
    dtype = parts[1] if len(parts) > 1 else DEFAULT_OS_DISK_TYPE
    if dtype in ("na", "none", ""):
        return 0, "", 0
    try:
        size = int(float(parts[2])) if len(parts) > 2 else 0
    except ValueError:
        size = 0
    return count, dtype, size


def vm_count_from_config(info: Dict[str, str]) -> int:
    networks = info.get("cloud_numb_networks") or info.get("cloud_number_networks") or "0"
    try:
        n = int(float(str(networks).split()[0]))
    except ValueError:
        n = 0
    return 2 if n >= 1 else 1


def _truthy(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _looks_gpu_sku(sku: str) -> bool:
    s = (sku or "").upper()
    # Azure GPU families: NC, ND, NG, NV, and some HB with GPU — NC/ND/NV/NG.
    return bool(re.search(r"_N[CDGV]", s)) or "GPU" in s


def load_overrides(path: Optional[str] = None) -> List[Dict[str, str]]:
    cfg = path or os.path.join(_REPO_ROOT, "config", "azure_pricing_overrides.cfg")
    rows: List[Dict[str, str]] = []
    if not os.path.isfile(cfg):
        return rows
    with open(cfg, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 6:
                continue
            rows.append(
                {
                    "resource_type": parts[0],
                    "sku": parts[1],
                    "region": parts[2],
                    "unit": parts[3],
                    "hourly_rate": parts[4],
                    "currency": parts[5],
                }
            )
    return rows


def override_rate(
    rows: List[Dict[str, str]], resource_type: str, sku: str, region: str
) -> Optional[Tuple[float, str, str]]:
    for row in rows:
        if row["resource_type"] != resource_type:
            continue
        if row["sku"] != sku and row["sku"] != "*":
            continue
        if row["region"] not in (region, "*"):
            continue
        return float(row["hourly_rate"]), row["currency"], row["unit"]
    return None


def resolve_rate(
    usage: ResourceUsage,
    *,
    overrides: List[Dict[str, str]],
    instance_cost: Optional[float] = None,
    vm_lookup: Optional[Callable[..., float]] = None,
    disk_lookup: Optional[Callable[..., float]] = None,
    pip_lookup: Optional[Callable[..., float]] = None,
    spot: bool = False,
    rate_cache: Optional[Dict[str, Optional[float]]] = None,
) -> Tuple[Optional[float], str, str, str]:
    """
    Returns (hourly_rate, pricing_source, currency, extra_calc_note).
    Disk rates are USD per disk-hour (quantity is 1).
    """
    resource_type = usage.resource_type
    sku = usage.sku
    region = usage.region
    hit = override_rate(overrides, resource_type, sku, region)
    if hit:
        rate, currency, _unit = hit
        return rate, "pricing_override", currency, ""

    if resource_type == "vm" and instance_cost is not None and instance_cost > 0:
        return instance_cost, "run_instance_cost", CURRENCY, ""

    if resource_type == "vm" and vm_lookup is not None:
        cache_key = f"vm:{sku}:{region}:spot={int(spot)}"
        if rate_cache is not None and cache_key in rate_cache:
            rate = rate_cache[cache_key]
            return (
                rate,
                ("azure_retail_prices" if rate is not None else "unavailable"),
                CURRENCY,
                "",
            )
        try:
            rate = float(vm_lookup(sku, region, spot=spot))
            if rate_cache is not None:
                rate_cache[cache_key] = rate
            return rate, "azure_retail_prices", CURRENCY, ""
        except Exception as exc:  # noqa: BLE001
            if rate_cache is not None:
                rate_cache[cache_key] = None
            return None, f"retail_error:{exc}", CURRENCY, ""

    if resource_type == "volume" and disk_lookup is not None:
        size = usage.disk_size_gb or 0
        if size <= 0:
            return None, "unavailable", CURRENCY, "disk size unknown — not guessed"
        cache_key = f"volume:{sku}:{region}:{size}"
        if rate_cache is not None and cache_key in rate_cache:
            rate = rate_cache[cache_key]
            return (
                rate,
                ("azure_retail_prices" if rate is not None else "unavailable"),
                CURRENCY,
                "",
            )
        try:
            rate = float(disk_lookup(sku or DEFAULT_OS_DISK_TYPE, region, size))
            if rate_cache is not None:
                rate_cache[cache_key] = rate
            note = (
                f"disk monthly÷{HOURS_PER_MONTH:.4f}h → ${rate:.6f}/hour"
            )
            return rate, "azure_retail_prices", CURRENCY, note
        except Exception as exc:  # noqa: BLE001
            if rate_cache is not None:
                rate_cache[cache_key] = None
            return None, f"retail_error:{exc}", CURRENCY, ""

    if resource_type == "public_ip" and pip_lookup is not None:
        cache_key = f"pip:{sku}:{region}"
        if rate_cache is not None and cache_key in rate_cache:
            rate = rate_cache[cache_key]
            return (
                rate,
                ("azure_retail_prices" if rate is not None else "unavailable"),
                CURRENCY,
                "",
            )
        try:
            rate = float(pip_lookup(region, sku=sku or "Basic"))
            if rate_cache is not None:
                rate_cache[cache_key] = rate
            return rate, "azure_retail_prices", CURRENCY, ""
        except Exception as exc:  # noqa: BLE001
            if rate_cache is not None:
                rate_cache[cache_key] = None
            return None, f"retail_error:{exc}", CURRENCY, ""

    return None, "unavailable", CURRENCY, ""


def calculate_resource_cost(
    usage: ResourceUsage,
    hourly_rate: Optional[float],
    pricing_source: str,
    currency: str = CURRENCY,
    extra_note: str = "",
) -> ResourceCost:
    hours = hours_from_seconds(usage.runtime_seconds)
    if hourly_rate is None:
        return ResourceCost(
            usage=usage,
            hourly_rate=None,
            daily_rate=None,
            total_cost=None,
            currency=currency,
            pricing_source=pricing_source,
            calculation=(
                f"{usage.resource_name}: runtime {usage.runtime_seconds}s "
                f"({hours:.6f} h) × quantity {usage.quantity}; "
                "rate unavailable — cost not guessed"
                + (f"; {extra_note}" if extra_note else "")
            ),
        )
    daily = hourly_rate * 24.0
    total = usage.quantity * hours * hourly_rate
    calc = (
        f"{usage.resource_name}: {usage.runtime_seconds} seconds "
        f"= {hours:.6f} hours; quantity {usage.quantity}; "
        f"rate {hourly_rate} {currency}/hour ({pricing_source}); "
        f"{usage.quantity} × {hours:.6f} × {hourly_rate} = {total:.6f}"
    )
    if extra_note:
        calc += f"; {extra_note}"
    if usage.runtime_is_estimate:
        calc += " [runtime is an estimate]"
    return ResourceCost(
        usage=usage,
        hourly_rate=hourly_rate,
        daily_rate=daily,
        total_cost=total,
        currency=currency,
        pricing_source=pricing_source,
        calculation=calc,
    )


def _unix(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


AZURE_NOT_BILLABLE_TYPES = {
    "azurerm_resource_group": "Resource group is not billed independently",
    "azurerm_virtual_network": "VNet is not billed independently",
    "azurerm_subnet": "Subnet is not billed independently",
    "azurerm_network_security_group": "NSG is not billed independently",
    "azurerm_network_security_rule": "NSG rules are not billed",
    "azurerm_network_interface": "NIC is not billed independently",
    "azurerm_subnet_network_security_group_association": "Association is not billed",
    "azurerm_virtual_machine_data_disk_attachment": "Attachment is not a billed SKU",
    "azurerm_proximity_placement_group": "PPG is not billed independently",
    "random_id": "Terraform helper; not an Azure SKU",
}


def discover_window(
    run_dir: str,
    configured_runtime_seconds: Optional[int] = None,
) -> Tuple[Optional[int], Optional[int], int, str, bool, List[str]]:
    warnings: List[str] = []
    life = parse_kv_file(os.path.join(run_dir, "instance_lifecycle"))
    start = _unix(
        life.get("terraform_apply_end_unix")
        or life.get("create_end_unix")
        or life.get("terraform_apply_start_unix")
        or life.get("create_start_unix")
    )
    end = _unix(
        life.get("terraform_destroy_end_unix")
        or life.get("terraform_destroy_start_unix")
        or life.get("terminate_end_unix")
        or life.get("terminate_start_unix")
    )
    source = "azure_lifecycle"
    if life.get("terraform_apply_end_unix") or life.get("terraform_destroy_end_unix"):
        source = "terraform_apply_to_destroy"
    if start is not None and end is not None:
        seconds, note = runtime_seconds(start, end)
        if note == "end_before_start":
            warnings.append("lifecycle end is before start; runtime set to 0")
        return start, end, seconds, source, False, warnings

    tests = parse_test_times(os.path.join(run_dir, "test_times"))
    if tests:
        seconds = sum(t[1] for t in tests)
        warnings.append(
            "Azure instance lifecycle timestamps missing; "
            "using Zathras test_times (does not include provision/teardown)"
        )
        return None, None, seconds, "zathras_test_times", True, warnings

    if configured_runtime_seconds is not None:
        warnings.append("Using --configured-runtime-seconds; this is an estimate")
        return None, None, int(configured_runtime_seconds), "configured_runtime", True, warnings

    warnings.append("No lifecycle timestamps, test_times, or configured runtime")
    return None, None, 0, "missing", False, warnings


def _walk_tf_resources(module: Dict[str, Any]) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    for resource in module.get("resources") or []:
        found.append(resource)
    for child in module.get("child_modules") or []:
        found.extend(_walk_tf_resources(child))
    return found


def load_terraform_inventory(run_dir: str) -> Optional[Dict[str, Any]]:
    for rel in ("terraform_inventory.json", os.path.join("tf", "terraform_inventory.json")):
        path = os.path.join(run_dir, rel)
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            try:
                with open(path, encoding="utf-8") as fh:
                    return json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
    return None


def _os_disk_size(vals: Dict[str, Any]) -> Tuple[Optional[int], str]:
    os_disk = vals.get("os_disk") or {}
    if isinstance(os_disk, list) and os_disk:
        os_disk = os_disk[0] if isinstance(os_disk[0], dict) else {}
    if not isinstance(os_disk, dict):
        return None, DEFAULT_OS_DISK_TYPE
    size = os_disk.get("disk_size_gb") or os_disk.get("disk_size")
    sat = os_disk.get("storage_account_type") or DEFAULT_OS_DISK_TYPE
    if size:
        try:
            return int(size), str(sat)
        except (TypeError, ValueError):
            pass
    return None, str(sat)


def resources_from_terraform_inventory(
    doc: Dict[str, Any],
    *,
    region: str,
    start: Optional[int],
    end: Optional[int],
    seconds: int,
    source: str,
    estimate: bool,
    warnings: Optional[List[str]] = None,
) -> List[ResourceUsage]:
    values = doc.get("values") or {}
    root = values.get("root_module") or {}
    usages: List[ResourceUsage] = []
    warn = warnings if warnings is not None else []
    for resource in _walk_tf_resources(root):
        if resource.get("mode") == "data":
            continue
        rtype = resource.get("type") or ""
        address = resource.get("address") or rtype
        vals = resource.get("values") or {}
        rid = str(vals.get("id") or address)
        name = str(vals.get("name") or address)
        loc = str(vals.get("location") or region)

        if rtype == "azurerm_linux_virtual_machine":
            sku = str(vals.get("size") or "")
            usages.append(
                ResourceUsage(
                    resource_id=rid,
                    resource_type="vm",
                    resource_name=name or f"VM:{sku}",
                    sku=sku,
                    region=loc,
                    quantity=1,
                    start_time=start,
                    end_time=end,
                    runtime_seconds=seconds,
                    runtime_source=source,
                    runtime_is_estimate=estimate,
                    unit="INSTANCE_HOUR",
                    notes=f"terraform {address}",
                    billable=True,
                )
            )
            if _looks_gpu_sku(sku):
                warn.append(
                    f"{name}: GPU-capable SKU {sku}; GPU charge is included in the VM "
                    "Retail meter (no separate GPU line)"
                )
            boot_size, boot_type = _os_disk_size(vals)
            if boot_size is None:
                warn.append(
                    f"{name}: OS disk size missing from terraform state — "
                    "OS disk cost unavailable (not guessed)"
                )
                usages.append(
                    ResourceUsage(
                        resource_id=f"{rid}:osdisk",
                        resource_type="volume",
                        resource_name=f"osdisk:{name}",
                        sku=boot_type,
                        region=loc,
                        quantity=1,
                        start_time=start,
                        end_time=end,
                        runtime_seconds=seconds,
                        runtime_source=source,
                        runtime_is_estimate=True,
                        unit="DISK_HOUR",
                        notes="OS disk size unknown",
                        billable=True,
                        disk_size_gb=None,
                    )
                )
            else:
                usages.append(
                    ResourceUsage(
                        resource_id=f"{rid}:osdisk",
                        resource_type="volume",
                        resource_name=f"osdisk:{name}",
                        sku=boot_type,
                        region=loc,
                        quantity=1,
                        start_time=start,
                        end_time=end,
                        runtime_seconds=seconds,
                        runtime_source=source,
                        runtime_is_estimate=estimate,
                        unit="DISK_HOUR",
                        notes=f"OS disk {boot_size} GB {boot_type} from terraform",
                        billable=True,
                        disk_size_gb=boot_size,
                    )
                )
        elif rtype == "azurerm_managed_disk":
            sat = str(vals.get("storage_account_type") or DEFAULT_OS_DISK_TYPE)
            size = vals.get("disk_size_gb") or vals.get("disk_size") or 0
            try:
                size_i = int(size)
            except (TypeError, ValueError):
                size_i = 0
            usages.append(
                ResourceUsage(
                    resource_id=rid,
                    resource_type="volume",
                    resource_name=name,
                    sku=sat,
                    region=loc,
                    quantity=1,
                    start_time=start,
                    end_time=end,
                    runtime_seconds=seconds,
                    runtime_source=source,
                    runtime_is_estimate=estimate or size_i <= 0,
                    unit="DISK_HOUR",
                    notes=f"terraform {address}; {size_i} GB",
                    billable=True,
                    disk_size_gb=size_i if size_i > 0 else None,
                )
            )
        elif rtype == "azurerm_public_ip":
            pip_sku = vals.get("sku") or "Basic"
            if isinstance(pip_sku, dict):
                pip_sku = pip_sku.get("name") or "Basic"
            usages.append(
                ResourceUsage(
                    resource_id=rid,
                    resource_type="public_ip",
                    resource_name=name,
                    sku=str(pip_sku),
                    region=loc,
                    quantity=1,
                    start_time=start,
                    end_time=end,
                    runtime_seconds=seconds,
                    runtime_source=source,
                    runtime_is_estimate=estimate,
                    unit="IP_HOUR",
                    notes=f"terraform {address}",
                    billable=True,
                )
            )
        else:
            reason = AZURE_NOT_BILLABLE_TYPES.get(
                rtype, "Not classified as an independently billed Azure SKU"
            )
            usages.append(
                ResourceUsage(
                    resource_id=rid or address,
                    resource_type="not_billed",
                    resource_name=name or address,
                    sku=rtype,
                    region=loc,
                    quantity=0,
                    start_time=start,
                    end_time=end,
                    runtime_seconds=seconds,
                    runtime_source=source,
                    runtime_is_estimate=estimate,
                    unit="NONE",
                    notes=reason,
                    billable=False,
                )
            )
    return usages


def discover_azure_resources(
    run_dir: str,
    *,
    configured_runtime_seconds: Optional[int] = None,
) -> Tuple[Dict[str, Any], List[ResourceUsage], List[str]]:
    info = parse_config_info(os.path.join(run_dir, "ansible_vars_main.yml"))
    if not info:
        raise CostError(f"No ansible_vars_main.yml in {run_dir}")
    if info.get("system_type") != "azure":
        raise CostError(f"system_type is {info.get('system_type')!r}, not azure")

    region = info.get("cloud_region") or ""
    sku = info.get("host_or_cloud_inst") or info.get("host_config") or ""
    run_label = info.get("run_label") or os.path.basename(os.path.abspath(run_dir))
    vm_n = vm_count_from_config(info)
    disk_count, disk_type, disk_size = parse_cloud_disks(info.get("cloud_disks", "none"))
    spot = (
        _truthy(info.get("use_spot"))
        or _truthy(info.get("spot_price"))
        or (info.get("vm_type") or "").lower() == "preemptible"
        or (
            str(info.get("spot_start_price") or "0") not in ("0", "0.0", "")
        )
    )

    start, end, seconds, source, estimate, warnings = discover_window(
        run_dir, configured_runtime_seconds=configured_runtime_seconds
    )

    status = "completed"
    if os.path.isfile(os.path.join(run_dir, "cpu_type_failure")):
        status = "failed"
    elif not os.path.isfile(os.path.join(run_dir, "test_returned")):
        status = "partial"

    header: Dict[str, Any] = {
        "run_id": run_label,
        "start_time": start,
        "end_time": end,
        "runtime_seconds": seconds,
        "runtime_source": source,
        "status": status,
        "region": region,
        "sku": sku,
        "spot": spot,
    }

    tf_doc = load_terraform_inventory(run_dir)
    if tf_doc:
        resources = resources_from_terraform_inventory(
            tf_doc,
            region=region,
            start=start,
            end=end,
            seconds=seconds,
            source=source,
            estimate=estimate,
            warnings=warnings,
        )
        return header, resources, warnings

    warnings.append(
        "terraform_inventory.json missing; inferring resources from ansible_vars"
    )
    resources: List[ResourceUsage] = []
    for idx in range(vm_n):
        name = f"{run_label}-vm-{idx}"
        resources.append(
            ResourceUsage(
                resource_id=f"inferred-vm-{idx}",
                resource_type="vm",
                resource_name=name,
                sku=sku,
                region=region,
                quantity=1,
                start_time=start,
                end_time=end,
                runtime_seconds=seconds,
                runtime_source=source,
                runtime_is_estimate=estimate,
                unit="INSTANCE_HOUR",
                notes="inferred from ansible_vars",
                billable=True,
            )
        )
        if _looks_gpu_sku(sku):
            warnings.append(
                f"{name}: GPU-capable SKU {sku}; GPU charge is included in the VM meter"
            )
        # OS disk size unknown without terraform — do not invent GB.
        warnings.append(
            f"{name}: OS disk size unknown without terraform inventory — "
            "OS disk cost unavailable"
        )
        resources.append(
            ResourceUsage(
                resource_id=f"inferred-osdisk-{idx}",
                resource_type="volume",
                resource_name=f"osdisk:{name}",
                sku=DEFAULT_OS_DISK_TYPE,
                region=region,
                quantity=1,
                start_time=start,
                end_time=end,
                runtime_seconds=seconds,
                runtime_source=source,
                runtime_is_estimate=True,
                unit="DISK_HOUR",
                notes="OS disk size unknown (ansible fallback)",
                billable=True,
                disk_size_gb=None,
            )
        )
        resources.append(
            ResourceUsage(
                resource_id=f"inferred-pip-{idx}",
                resource_type="public_ip",
                resource_name=f"{run_label}-publicip-{idx:02d}",
                sku="Basic",
                region=region,
                quantity=1,
                start_time=start,
                end_time=end,
                runtime_seconds=seconds,
                runtime_source=source,
                runtime_is_estimate=estimate,
                unit="IP_HOUR",
                notes="inferred public IP (Dynamic Basic)",
                billable=True,
            )
        )
        if disk_count > 0 and disk_size > 0:
            for di in range(disk_count):
                resources.append(
                    ResourceUsage(
                        resource_id=f"inferred-datadisk-{idx}-{di}",
                        resource_type="volume",
                        resource_name=f"datadisk-{idx}-{di}",
                        sku=disk_type or DEFAULT_OS_DISK_TYPE,
                        region=region,
                        quantity=1,
                        start_time=start,
                        end_time=end,
                        runtime_seconds=seconds,
                        runtime_source=source,
                        runtime_is_estimate=estimate,
                        unit="DISK_HOUR",
                        notes=f"{disk_size} GB {disk_type} from cloud_disks",
                        billable=True,
                        disk_size_gb=disk_size,
                    )
                )
    return header, resources, warnings


def _instance_cost_file(run_dir: str) -> Optional[float]:
    path = os.path.join(run_dir, "instance_cost")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().strip().splitlines()
    if not lines:
        return None
    try:
        val = float(lines[0].split()[0])
    except ValueError:
        return None
    return val if val > 0 else None


def price_run(
    header: Dict[str, Any],
    usages: List[ResourceUsage],
    *,
    overrides: Optional[List[Dict[str, str]]] = None,
    instance_cost: Optional[float] = None,
    vm_lookup: Optional[Callable[..., float]] = None,
    disk_lookup: Optional[Callable[..., float]] = None,
    pip_lookup: Optional[Callable[..., float]] = None,
    warnings: Optional[List[str]] = None,
) -> RunCost:
    overrides = overrides if overrides is not None else load_overrides()
    priced: List[ResourceCost] = []
    warn = list(warnings or [])
    rate_cache: Dict[str, Optional[float]] = {}
    spot = bool(header.get("spot"))
    for usage in usages:
        if not usage.billable:
            priced.append(
                ResourceCost(
                    usage=usage,
                    hourly_rate=0.0,
                    daily_rate=0.0,
                    total_cost=0.0,
                    currency=CURRENCY,
                    pricing_source="not_billable",
                    calculation=f"{usage.resource_name}: not billed ({usage.notes})",
                )
            )
            continue
        rate, source, currency, extra = resolve_rate(
            usage,
            overrides=overrides,
            instance_cost=instance_cost if usage.resource_type == "vm" else None,
            vm_lookup=vm_lookup,
            disk_lookup=disk_lookup,
            pip_lookup=pip_lookup,
            spot=spot,
            rate_cache=rate_cache,
        )
        if rate is None:
            warn.append(
                f"{usage.resource_name}: no {usage.resource_type} rate for "
                f"sku={usage.sku} region={usage.region}"
            )
        priced.append(
            calculate_resource_cost(
                usage, rate, source, currency=currency, extra_note=extra
            )
        )

    known = [r.total_cost for r in priced if r.total_cost is not None]
    total = sum(known) if known else None
    hours = hours_from_seconds(header["runtime_seconds"])
    avg = (total / hours) if total is not None and hours > 0 else None
    est24 = None
    if header["runtime_seconds"] > 0 and total is not None and hours:
        est24 = total / hours * 24.0

    categories = {"vm": 0.0, "gpu": 0.0, "storage": 0.0, "network": 0.0, "other": 0.0}
    for row in priced:
        rtype = row.usage.resource_type
        if rtype == "not_billed" or row.total_cost is None:
            continue
        if rtype == "vm":
            categories["vm"] += row.total_cost
        elif rtype == "volume":
            categories["storage"] += row.total_cost
        elif rtype == "public_ip":
            categories["network"] += row.total_cost
        else:
            categories["other"] += row.total_cost

    return RunCost(
        run_id=header["run_id"],
        start_time=header.get("start_time"),
        end_time=header.get("end_time"),
        runtime_seconds=header["runtime_seconds"],
        runtime_source=header["runtime_source"],
        status=header.get("status") or "unknown",
        currency=CURRENCY,
        resources=priced,
        total_cost=total,
        average_cost_per_hour=avg,
        estimated_24h_cost=est24,
        category_totals=categories,
        warnings=warn,
    )


def _fmt_money(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"${value:.4f}"


def _fmt_hours(seconds: int) -> str:
    hours = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours}h {mins}m {secs}s"


def _cli_type_label(resource_type: str) -> str:
    return {
        "vm": "vm",
        "volume": "volume",
        "public_ip": "pip",
        "not_billed": "other",
    }.get(resource_type, resource_type[:8])


def _cli_short_name(name: str, width: int = 40) -> str:
    if len(name) <= width:
        return name
    if width <= 1:
        return name[:width]
    return name[: width - 1] + "…"


def _cli_what_ran(run: RunCost) -> str:
    counts: Dict[str, int] = {}
    vm_skus: List[str] = []
    for row in run.resources:
        if not row.usage.billable:
            continue
        label = _cli_type_label(row.usage.resource_type)
        counts[label] = counts.get(label, 0) + 1
        if row.usage.resource_type == "vm" and row.usage.sku:
            vm_skus.append(row.usage.sku)
    if not counts:
        return "no billable resources"
    parts = []
    for key in ("vm", "volume", "pip"):
        n = counts.pop(key, 0)
        if not n:
            continue
        if key == "vm" and vm_skus:
            unique = sorted(set(vm_skus))
            sku_txt = ", ".join(unique[:3])
            if len(unique) > 3:
                sku_txt += ", …"
            parts.append(f"{n} VM ({sku_txt})" if n == 1 else f"{n} VMs ({sku_txt})")
        elif key == "volume":
            parts.append(f"{n} disk" if n == 1 else f"{n} disks")
        elif key == "pip":
            parts.append(f"{n} public IP" if n == 1 else f"{n} public IPs")
    for key, n in sorted(counts.items()):
        parts.append(f"{n} {key}")
    return " + ".join(parts)


def format_cli(run: RunCost) -> str:
    cat = run.category_totals
    billable = [r for r in run.resources if r.usage.billable]
    not_billed = [r.usage.resource_name for r in run.resources if not r.usage.billable]

    lines = [
        "Zathras Run Cost — TL;DR",
        "========================",
        f"Run        : {run.run_id}  ({_fmt_hours(run.runtime_seconds)})",
        f"What ran   : {_cli_what_ran(run)}",
        f"TOTAL      : {_fmt_money(run.total_cost)} {run.currency}",
        f"  VM         {_fmt_money(cat.get('vm'))}",
        f"  Storage    {_fmt_money(cat.get('storage'))}",
        f"  Network    {_fmt_money(cat.get('network'))}",
        f"  GPU        {_fmt_money(cat.get('gpu'))}  (included in VM SKU when applicable)",
        f"  Other      {_fmt_money(cat.get('other'))}",
        "",
        f"(~{_fmt_money(run.average_cost_per_hour)} / hour of wall-clock run time)",
        "",
        "········································································",
        "Details (for audit / deep dive)",
        "········································································",
        "",
        f"Status     : {run.status}",
        f"Start      : {_fmt_epoch(run.start_time)}",
        f"End        : {_fmt_epoch(run.end_time)}",
        f"Runtime    : {_fmt_hours(run.runtime_seconds)} "
        f"({hours_from_seconds(run.runtime_seconds):.4f} h, source={run.runtime_source})",
        f"Resources  : {len(run.resources)} ({len(billable)} billable)",
        "",
        f"{'TYPE':<8} {'NAME':<40} {'SKU':<18} {'RUNTIME':<12} {'RATE/HR':<12} {'COST':>10}",
        "-" * 104,
    ]
    for row in billable:
        rate = (
            _fmt_money(row.hourly_rate) + "/hr"
            if row.hourly_rate is not None
            else "n/a"
        )
        cost = _fmt_money(row.total_cost)
        sku = (row.usage.sku or "-")[:18]
        lines.append(
            f"{_cli_type_label(row.usage.resource_type):<8} "
            f"{_cli_short_name(row.usage.resource_name, 40):<40} "
            f"{sku:<18} "
            f"{_fmt_hours(row.usage.runtime_seconds):<12} "
            f"{rate:<12} {cost:>10}"
        )
    lines.append("-" * 104)
    lines.extend(
        [
            f"TOTAL COST    : {_fmt_money(run.total_cost)} {run.currency}",
            f"Average cost/hour (total / run runtime): {_fmt_money(run.average_cost_per_hour)}",
            "This is not the sum of resource hourly rates when lifetimes differ.",
            f"Estimated 24-hour cost (not an Azure daily SKU): {_fmt_money(run.estimated_24h_cost)}",
        ]
    )
    if not_billed:
        lines.append("")
        lines.append(
            "Not billed (created, no separate line item): " + ", ".join(not_billed)
        )
    if run.warnings:
        lines.append("")
        lines.append("Notes:")
        for w in run.warnings:
            lines.append(f"  - {w}")
    lines.append("")
    lines.append("Audit trail:")
    for row in run.resources:
        lines.append(f"  {row.calculation}")
    return "\n".join(lines) + "\n"


def _fmt_epoch(ts: Optional[int]) -> str:
    if ts is None:
        return "unknown"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def run_to_json(run: RunCost) -> Dict[str, Any]:
    resources = []
    for row in run.resources:
        u = row.usage
        resources.append(
            {
                "resource_id": u.resource_id,
                "resource_type": u.resource_type,
                "resource_name": u.resource_name,
                "sku": u.sku,
                "region": u.region,
                "quantity": u.quantity,
                "disk_size_gb": u.disk_size_gb,
                "start_time": u.start_time,
                "end_time": u.end_time,
                "runtime_seconds": u.runtime_seconds,
                "runtime_hours": hours_from_seconds(u.runtime_seconds),
                "runtime_source": u.runtime_source,
                "runtime_is_estimate": u.runtime_is_estimate,
                "hourly_rate": row.hourly_rate,
                "daily_rate": row.daily_rate,
                "total_cost": row.total_cost,
                "currency": row.currency,
                "pricing_source": row.pricing_source,
                "calculation": row.calculation,
                "attribution": u.attribution,
                "notes": u.notes,
                "billable": u.billable,
            }
        )
    return {
        "run_id": run.run_id,
        "cloud": "azure",
        "start_time": run.start_time,
        "end_time": run.end_time,
        "runtime_seconds": run.runtime_seconds,
        "runtime_hours": hours_from_seconds(run.runtime_seconds),
        "runtime_source": run.runtime_source,
        "status": run.status,
        "currency": run.currency,
        "total_cost": run.total_cost,
        "average_cost_per_hour": run.average_cost_per_hour,
        "estimated_24h_cost": run.estimated_24h_cost,
        "category_totals": run.category_totals,
        "warnings": run.warnings,
        "resources": resources,
    }


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS zathras_run (
            run_id TEXT PRIMARY KEY,
            cloud TEXT,
            start_time INTEGER,
            end_time INTEGER,
            runtime_seconds INTEGER,
            runtime_source TEXT,
            status TEXT,
            currency TEXT,
            total_cost REAL,
            average_cost_per_hour REAL,
            estimated_24h_cost REAL
        );
        CREATE TABLE IF NOT EXISTS run_resource (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            resource_id TEXT,
            resource_type TEXT,
            resource_name TEXT,
            sku TEXT,
            region TEXT,
            quantity REAL,
            runtime_seconds INTEGER,
            hourly_rate REAL,
            total_cost REAL,
            currency TEXT,
            pricing_source TEXT,
            calculation TEXT,
            billable INTEGER
        );
        """
    )


def persist(run: RunCost, db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        ensure_schema(conn)
        conn.execute(
            """
            INSERT OR REPLACE INTO zathras_run (
                run_id, cloud, start_time, end_time, runtime_seconds, runtime_source,
                status, currency, total_cost, average_cost_per_hour, estimated_24h_cost
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                "azure",
                run.start_time,
                run.end_time,
                run.runtime_seconds,
                run.runtime_source,
                run.status,
                run.currency,
                run.total_cost,
                run.average_cost_per_hour,
                run.estimated_24h_cost,
            ),
        )
        conn.execute("DELETE FROM run_resource WHERE run_id = ?", (run.run_id,))
        for row in run.resources:
            u = row.usage
            conn.execute(
                """
                INSERT INTO run_resource (
                    run_id, resource_id, resource_type, resource_name, sku, region,
                    quantity, runtime_seconds, hourly_rate, total_cost, currency,
                    pricing_source, calculation, billable
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    u.resource_id,
                    u.resource_type,
                    u.resource_name,
                    u.sku,
                    u.region,
                    u.quantity,
                    u.runtime_seconds,
                    row.hourly_rate,
                    row.total_cost,
                    row.currency,
                    row.pricing_source,
                    row.calculation,
                    1 if u.billable else 0,
                ),
            )
        conn.commit()
    finally:
        conn.close()


_LOOKUP_DEFAULT = object()


def cost_run_dir(
    run_dir: str,
    *,
    overrides_path: Optional[str] = None,
    configured_runtime_seconds: Optional[int] = None,
    vm_lookup: Any = _LOOKUP_DEFAULT,
    disk_lookup: Any = _LOOKUP_DEFAULT,
    pip_lookup: Any = _LOOKUP_DEFAULT,
    use_retail: bool = False,
) -> RunCost:
    header, usages, warnings = discover_azure_resources(
        run_dir, configured_runtime_seconds=configured_runtime_seconds
    )
    overrides = load_overrides(overrides_path)
    instance_cost = _instance_cost_file(run_dir)

    if vm_lookup is _LOOKUP_DEFAULT:
        vm_lookup = lookup_vm_hourly_price if use_retail else None
    if disk_lookup is _LOOKUP_DEFAULT:
        disk_lookup = lookup_managed_disk_hourly_price if use_retail else None
    if pip_lookup is _LOOKUP_DEFAULT:
        pip_lookup = (
            (lambda region, sku="Basic": lookup_public_ip_hourly_price(region, sku=sku))
            if use_retail
            else None
        )

    return price_run(
        header,
        usages,
        overrides=overrides,
        instance_cost=instance_cost,
        vm_lookup=vm_lookup,
        disk_lookup=disk_lookup,
        pip_lookup=pip_lookup,
        warnings=warnings,
    )


def find_latest_azure_run(root: str) -> Optional[str]:
    latest: Optional[Tuple[float, str]] = None
    for dirpath, _dirnames, filenames in os.walk(root):
        if "ansible_vars_main.yml" not in filenames:
            continue
        info = parse_config_info(os.path.join(dirpath, "ansible_vars_main.yml"))
        if info.get("system_type") != "azure":
            continue
        stamp = os.path.getmtime(os.path.join(dirpath, "ansible_vars_main.yml"))
        for name in ("instance_lifecycle", "cost_report.json", "test_times"):
            path = os.path.join(dirpath, name)
            if os.path.isfile(path):
                stamp = max(stamp, os.path.getmtime(path))
        if latest is None or stamp > latest[0]:
            latest = (stamp, dirpath)
    return latest[1] if latest else None


def attach_cost_to_results(run_dir: str) -> None:
    reports = [
        os.path.join(run_dir, "cost_report.json"),
        os.path.join(run_dir, "cost_report.txt"),
    ]
    reports = [p for p in reports if os.path.isfile(p)]
    if not reports:
        return
    try:
        tar_path = os.path.join(run_dir, "azure_cost.tar")
        subprocess.run(
            ["tar", "cf", tar_path] + [os.path.basename(p) for p in reports],
            cwd=run_dir,
            check=False,
            timeout=30,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
    names = [os.path.basename(p) for p in reports]
    for zip_path in glob.glob(os.path.join(run_dir, "results_*.zip")):
        try:
            subprocess.run(
                ["zip", "-q", "-u", zip_path] + names,
                cwd=run_dir,
                check=False,
                timeout=30,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
    for tar_path in glob.glob(os.path.join(run_dir, "results_*.tar")):
        try:
            subprocess.run(
                ["tar", "rf", tar_path] + names,
                cwd=run_dir,
                check=False,
                timeout=30,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Calculate Azure cost for a Zathras run"
    )
    parser.add_argument("run_dir", nargs="?", help="Zathras run directory")
    parser.add_argument("--latest", action="store_true", help="Use newest Azure run under cwd")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument("--record", action="store_true", help="Write cost_report.json and sqlite")
    parser.add_argument("--db", default="", help="SQLite path")
    parser.add_argument("--overrides", default="", help="Pricing override file")
    parser.add_argument(
        "--configured-runtime-seconds",
        type=int,
        default=None,
        help="Runtime estimate when timestamps are missing",
    )
    parser.add_argument(
        "--use-catalog",
        "--use-retail",
        dest="use_retail",
        action="store_true",
        help="Query Azure Retail Prices API when instance_cost / overrides miss",
    )
    parser.add_argument(
        "--attach-results",
        action="store_true",
        help="Copy cost reports into results_*.zip / results_*.tar if present",
    )
    parser.add_argument(
        "--fail-open",
        action="store_true",
        help="Exit 0 on calculator errors so benchmark runs are not failed",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    def _fail(msg: str, code: int = 1) -> int:
        print(f"ERROR: {msg}", file=sys.stderr)
        return 0 if args.fail_open else code

    run_dir = args.run_dir
    if args.latest:
        run_dir = find_latest_azure_run(os.getcwd())
        if not run_dir:
            return _fail("no Azure Zathras run directories found")
    if not run_dir:
        parser.error("run_dir is required unless --latest is set")
    if not os.path.isdir(run_dir):
        return _fail(f"not a directory: {run_dir}")

    try:
        run = cost_run_dir(
            run_dir,
            overrides_path=args.overrides or None,
            configured_runtime_seconds=args.configured_runtime_seconds,
            use_retail=args.use_retail,
        )
    except Exception as exc:  # noqa: BLE001
        return _fail(str(exc))

    payload = run_to_json(run)
    if args.record:
        try:
            with open(os.path.join(run_dir, "cost_report.json"), "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
                fh.write("\n")
            with open(os.path.join(run_dir, "cost_report.txt"), "w", encoding="utf-8") as fh:
                fh.write(format_cli(run))
            db_path = args.db or os.path.join(run_dir, "zathras_cost.db")
            persist(run, db_path)
        except Exception as exc:  # noqa: BLE001
            return _fail(f"failed to record cost: {exc}")
        if args.attach_results:
            attach_cost_to_results(run_dir)

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(format_cli(run), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
