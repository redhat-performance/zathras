#!/usr/bin/env python3
#
# IBM Cloud cost tracking for a Zathras run directory.
#
# Pricing is never hard-coded in this file. Rates come from, in order:
#   1) config/ibm_pricing_overrides.cfg
#   2) the run's instance_cost file (captured at start from the catalog)
#   3) IBM Global Catalog (VSI / GPU only)
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
import json
import os
import re
import sqlite3
import subprocess
import sys
import glob
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

SECONDS_PER_HOUR = 3600.0
CURRENCY = "USD"
DEFAULT_BOOT_GB = 100
DEFAULT_BOOT_PROFILE = "general-purpose"

_UTILS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_UTILS_DIR, "..", ".."))
if _UTILS_DIR not in sys.path:
    sys.path.insert(0, _UTILS_DIR)

try:
    from ibm_instance_price import (
        lookup_hourly_price,
        lookup_volume_gb_hour_price,
        lookup_floating_ip_hourly_price,
    )
except ImportError:  # pragma: no cover
    lookup_hourly_price = None  # type: ignore
    lookup_volume_gb_hour_price = None  # type: ignore
    lookup_floating_ip_hourly_price = None  # type: ignore


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
    """
    Return (seconds, note).

    missing:
      zero — treat absent timestamps as 0 seconds
      error — raise CostError
    """
    if start is None or end is None:
        if missing == "error":
            raise CostError("missing timestamps")
        return 0, "missing_timestamps"
    if end < start:
        return 0, "end_before_start"
    return int(end - start), "ok"


def overlap_seconds(
    a_start: int, a_end: int, b_start: int, b_end: int
) -> int:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    return max(0, end - start)


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
    """Read config_info scalars from ansible_vars_main.yml without PyYAML."""
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
    """
    burden format: count:type:size:...
    Returns (count, profile, size_gb). Missing/none → (0, '', 0).
    """
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
    dtype = parts[1] if len(parts) > 1 else DEFAULT_BOOT_PROFILE
    try:
        size = int(float(parts[2])) if len(parts) > 2 else 0
    except ValueError:
        size = 0
    profile = DEFAULT_BOOT_PROFILE
    if dtype in ("gp3", "custom"):
        profile = "custom"
    elif dtype and dtype not in ("na",):
        profile = dtype
    return count, profile, size


def vm_count_from_config(info: Dict[str, str]) -> int:
    # Matches ibm_create/templates/tfvars.j2: extra networks ⇒ two VSIs.
    networks = info.get("cloud_numb_networks") or info.get("cloud_number_networks") or "0"
    try:
        n = int(float(str(networks).split()[0]))
    except ValueError:
        n = 0
    return 2 if n >= 1 else 1


def load_overrides(path: Optional[str] = None) -> List[Dict[str, str]]:
    cfg = path or os.path.join(_REPO_ROOT, "config", "ibm_pricing_overrides.cfg")
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
    resource_type: str,
    sku: str,
    region: str,
    *,
    overrides: List[Dict[str, str]],
    instance_cost: Optional[float] = None,
    catalog_lookup: Optional[Callable[[str, str], float]] = None,
    volume_lookup: Optional[Callable[[str, str], float]] = None,
    floating_ip_lookup: Optional[Callable[[str], float]] = None,
    gpu_hourly: Optional[float] = None,
    compute_hourly: Optional[float] = None,
    rate_cache: Optional[Dict[str, Optional[float]]] = None,
) -> Tuple[Optional[float], str, str]:
    """
    Returns (hourly_rate, pricing_source, currency).

    For volumes the rate is USD per GB-hour.
    For floating IPs the rate is USD per IP-hour.
    """
    hit = override_rate(overrides, resource_type, sku, region)
    if hit:
        rate, currency, _unit = hit
        return rate, "pricing_override", currency

    if resource_type == "gpu" and gpu_hourly is not None:
        return gpu_hourly, "ibm_global_catalog", CURRENCY
    if resource_type == "vm" and compute_hourly is not None:
        return compute_hourly, "ibm_global_catalog", CURRENCY
    if resource_type == "vm" and instance_cost is not None and instance_cost > 0:
        return instance_cost, "run_instance_cost", CURRENCY
    if resource_type == "vm" and catalog_lookup is not None:
        cache_key = f"vm:{sku}:{region}"
        if rate_cache is not None and cache_key in rate_cache:
            rate = rate_cache[cache_key]
            return rate, ("ibm_global_catalog" if rate is not None else "unavailable"), CURRENCY
        try:
            rate = float(catalog_lookup(sku, region))
            if rate_cache is not None:
                rate_cache[cache_key] = rate
            return rate, "ibm_global_catalog", CURRENCY
        except Exception as exc:  # noqa: BLE001
            if rate_cache is not None:
                rate_cache[cache_key] = None
            return None, f"catalog_error:{exc}", CURRENCY

    if resource_type == "volume" and volume_lookup is not None:
        cache_key = f"volume:{sku}:{region}"
        if rate_cache is not None and cache_key in rate_cache:
            rate = rate_cache[cache_key]
            return (
                rate,
                ("ibm_global_catalog" if rate is not None else "unavailable"),
                CURRENCY,
            )
        try:
            rate = float(volume_lookup(sku or DEFAULT_BOOT_PROFILE, region))
            if rate_cache is not None:
                rate_cache[cache_key] = rate
            return rate, "ibm_global_catalog", CURRENCY
        except Exception as exc:  # noqa: BLE001
            if rate_cache is not None:
                rate_cache[cache_key] = None
            return None, f"catalog_error:{exc}", CURRENCY

    if resource_type == "floating_ip" and floating_ip_lookup is not None:
        cache_key = f"fip:{region}"
        if rate_cache is not None and cache_key in rate_cache:
            rate = rate_cache[cache_key]
            return (
                rate,
                ("ibm_global_catalog" if rate is not None else "unavailable"),
                CURRENCY,
            )
        try:
            rate = float(floating_ip_lookup(region))
            if rate_cache is not None:
                rate_cache[cache_key] = rate
            return rate, "ibm_global_catalog", CURRENCY
        except Exception as exc:  # noqa: BLE001
            if rate_cache is not None:
                rate_cache[cache_key] = None
            return None, f"catalog_error:{exc}", CURRENCY

    return None, "unavailable", CURRENCY


def calculate_resource_cost(
    usage: ResourceUsage,
    hourly_rate: Optional[float],
    pricing_source: str,
    currency: str = CURRENCY,
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


IBM_BILLABLE_TYPES = {
    "ibm_is_instance": "vm",
    "ibm_is_volume": "volume",
    "ibm_is_floating_ip": "floating_ip",
}

IBM_NOT_BILLABLE_TYPES = {
    "ibm_is_vpc": "VPC has no separate instance hourly charge",
    "ibm_is_subnet": "Subnet is not billed independently",
    "ibm_is_security_group": "Security group is not billed independently",
    "ibm_is_security_group_rule": "Security group rules are not billed",
    "ibm_is_instance_volume_attachment": "Attachment is not a billed SKU",
    "ibm_is_ssh_key": "SSH keys are not billed as compute",
    "random_id": "Terraform helper; not an IBM SKU",
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
    source = "ibm_lifecycle"
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
            "IBM instance lifecycle timestamps missing; "
            "using Zathras test_times (does not include provision/teardown)"
        )
        return None, None, seconds, "zathras_test_times", True, warnings

    if configured_runtime_seconds is not None:
        warnings.append(
            "Using --configured-runtime-seconds; this is an estimate"
        )
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


def resources_from_terraform_inventory(
    doc: Dict[str, Any],
    *,
    region: str,
    start: Optional[int],
    end: Optional[int],
    seconds: int,
    source: str,
    estimate: bool,
) -> List[ResourceUsage]:
    """Map terraform show -json into billable / not-billable usage rows."""
    values = doc.get("values") or {}
    root = values.get("root_module") or {}
    usages: List[ResourceUsage] = []
    for resource in _walk_tf_resources(root):
        if resource.get("mode") == "data":
            continue
        rtype = resource.get("type") or ""
        address = resource.get("address") or rtype
        vals = resource.get("values") or {}
        rid = str(vals.get("id") or address)
        name = str(vals.get("name") or address)
        if rtype == "ibm_is_instance":
            sku = str(vals.get("profile") or "")
            boot = vals.get("boot_volume") or []
            boot_size = DEFAULT_BOOT_GB
            boot_estimate = True
            if boot and isinstance(boot, list) and isinstance(boot[0], dict):
                size = boot[0].get("size") or boot[0].get("capacity")
                if size:
                    boot_size = int(size)
                    boot_estimate = False
            usages.append(
                ResourceUsage(
                    resource_id=rid,
                    resource_type="vm",
                    resource_name=name or f"VSI:{sku}",
                    sku=sku,
                    region=region,
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
            gpu_profile = sku.lower().startswith("gx") or "gpu" in sku.lower()
            if gpu_profile:
                usages.append(
                    ResourceUsage(
                        resource_id=f"{rid}:gpu",
                        resource_type="gpu",
                        resource_name=f"GPU:{sku}",
                        sku=sku,
                        region=region,
                        quantity=1,
                        start_time=start,
                        end_time=end,
                        runtime_seconds=seconds,
                        runtime_source=source,
                        runtime_is_estimate=estimate,
                        unit="GPU_HOUR",
                        notes=f"GPU hours for terraform {address}",
                        billable=True,
                    )
                )
            usages.append(
                ResourceUsage(
                    resource_id=f"{rid}:boot",
                    resource_type="volume",
                    resource_name=f"boot:{name}",
                    sku=DEFAULT_BOOT_PROFILE,
                    region=region,
                    quantity=boot_size,
                    start_time=start,
                    end_time=end,
                    runtime_seconds=seconds,
                    runtime_source=source,
                    runtime_is_estimate=boot_estimate or estimate,
                    unit="GB_HOUR",
                    notes=(
                        f"boot volume {boot_size} GB from terraform"
                        if not boot_estimate
                        else f"boot volume size estimated {boot_size} GB"
                    ),
                    billable=True,
                )
            )
        elif rtype == "ibm_is_volume":
            sku = str(vals.get("profile") or DEFAULT_BOOT_PROFILE)
            cap = vals.get("capacity") or vals.get("size") or 0
            usages.append(
                ResourceUsage(
                    resource_id=rid,
                    resource_type="volume",
                    resource_name=name,
                    sku=sku,
                    region=region,
                    quantity=float(cap) if cap else 0,
                    start_time=start,
                    end_time=end,
                    runtime_seconds=seconds,
                    runtime_source=source,
                    runtime_is_estimate=estimate,
                    unit="GB_HOUR",
                    notes=f"terraform {address}",
                    billable=True,
                )
            )
        elif rtype == "ibm_is_floating_ip":
            usages.append(
                ResourceUsage(
                    resource_id=rid,
                    resource_type="floating_ip",
                    resource_name=name,
                    sku="standard",
                    region=region,
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
            reason = IBM_NOT_BILLABLE_TYPES.get(
                rtype, "Not classified as an independently billed IBM SKU"
            )
            usages.append(
                ResourceUsage(
                    resource_id=rid or address,
                    resource_type="not_billed",
                    resource_name=name or address,
                    sku=rtype,
                    region=region,
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


def discover_ibm_resources(
    run_dir: str,
    *,
    configured_runtime_seconds: Optional[int] = None,
) -> Tuple[Dict[str, Any], List[ResourceUsage], List[str]]:
    info = parse_config_info(os.path.join(run_dir, "ansible_vars_main.yml"))
    if not info:
        raise CostError(f"No ansible_vars_main.yml in {run_dir}")
    if info.get("system_type") != "ibm":
        raise CostError(
            f"system_type is {info.get('system_type')!r}, not ibm"
        )

    meta = parse_kv_file(os.path.join(run_dir, "meta_data.yml"))
    # meta_data.yml is nested YAML; fall back to config_info.
    region = info.get("cloud_region") or meta.get("region") or ""
    zone = info.get("cloud_zone") or meta.get("zone") or ""
    sku = info.get("host_or_cloud_inst") or info.get("host_config") or ""
    run_label = info.get("run_label") or os.path.basename(os.path.abspath(run_dir))
    instance_id = meta.get("instance_id") or ""
    vm_n = vm_count_from_config(info)
    disk_count, disk_profile, disk_size = parse_cloud_disks(info.get("cloud_disks", "none"))

    start, end, seconds, source, estimate, warnings = discover_window(
        run_dir, configured_runtime_seconds
    )
    run_id = f"{run_label}:{sku}:{os.path.basename(os.path.abspath(run_dir))}"

    status = "completed"
    if os.path.isfile(os.path.join(run_dir, "cpu_type_failure")):
        status = "failed"
    elif not os.path.isfile(os.path.join(run_dir, "test_returned")):
        if os.path.isfile(os.path.join(run_dir, "test_started")):
            status = "partial"
        else:
            status = "unknown"

    header = {
        "run_id": run_id,
        "run_label": run_label,
        "sku": sku,
        "region": region,
        "zone": zone,
        "vm_count": vm_n,
        "start_time": start,
        "end_time": end,
        "runtime_seconds": seconds,
        "runtime_source": source,
        "status": status,
        "instance_id": instance_id,
    }

    inventory = load_terraform_inventory(run_dir)
    if inventory:
        usages = resources_from_terraform_inventory(
            inventory,
            region=region,
            start=start,
            end=end,
            seconds=seconds,
            source=source,
            estimate=estimate,
        )
        if usages:
            header["vm_count"] = sum(1 for u in usages if u.resource_type == "vm")
            return header, usages, warnings

    resources: List[ResourceUsage] = []
    gpu_profile = sku.lower().startswith("gx") or "gpu" in sku.lower()

    for idx in range(vm_n):
        rid = instance_id if instance_id and idx == 0 else f"{run_id}:vm:{idx}"
        # GPU profiles still bill a VSI; GPU hours are a second line if split.
        resources.append(
            ResourceUsage(
                resource_id=rid,
                resource_type="vm",
                resource_name=f"VSI-{idx}:{sku}",
                sku=sku,
                region=region,
                quantity=1,
                start_time=start,
                end_time=end,
                runtime_seconds=seconds,
                runtime_source=source,
                runtime_is_estimate=estimate,
                unit="INSTANCE_HOUR",
                notes=f"zone={zone}",
            )
        )
        if gpu_profile:
            resources.append(
                ResourceUsage(
                    resource_id=f"{rid}:gpu",
                    resource_type="gpu",
                    resource_name=f"GPU-{idx}:{sku}",
                    sku=sku,
                    region=region,
                    quantity=1,
                    start_time=start,
                    end_time=end,
                    runtime_seconds=seconds,
                    runtime_source=source,
                    runtime_is_estimate=estimate,
                    unit="GPU_HOUR",
                    notes="GPU hours split from the same VSI catalog metrics when available",
                )
            )
        resources.append(
            ResourceUsage(
                resource_id=f"{rid}:boot",
                resource_type="volume",
                resource_name=f"boot-volume-{idx}",
                sku=DEFAULT_BOOT_PROFILE,
                region=region,
                quantity=DEFAULT_BOOT_GB,
                start_time=start,
                end_time=end,
                runtime_seconds=seconds,
                runtime_source=source,
                runtime_is_estimate=True,
                unit="GB_HOUR",
                notes=(
                    f"IBM VPC default boot volume assumed {DEFAULT_BOOT_GB} GB "
                    f"{DEFAULT_BOOT_PROFILE} (not in Terraform); size is an estimate"
                ),
            )
        )
        resources.append(
            ResourceUsage(
                resource_id=f"{rid}:fip",
                resource_type="floating_ip",
                resource_name=f"floating-ip-{idx}",
                sku="standard",
                region=region,
                quantity=1,
                start_time=start,
                end_time=end,
                runtime_seconds=seconds,
                runtime_source=source,
                runtime_is_estimate=estimate,
                unit="IP_HOUR",
                notes="Allocated for the VSI lifetime; rate from override/catalog only",
            )
        )

    if disk_count and disk_size:
        for vmi in range(vm_n):
            for di in range(disk_count):
                resources.append(
                    ResourceUsage(
                        resource_id=f"{run_id}:data:{vmi}:{di}",
                        resource_type="volume",
                        resource_name=f"data-volume-{vmi}-{di}",
                        sku=disk_profile or DEFAULT_BOOT_PROFILE,
                        region=region,
                        quantity=disk_size,
                        start_time=start,
                        end_time=end,
                        runtime_seconds=seconds,
                        runtime_source=source,
                        runtime_is_estimate=estimate,
                        unit="GB_HOUR",
                        notes=f"{disk_size} GB {disk_profile} from cloud_disks",
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
    catalog_lookup: Optional[Callable[[str, str], float]] = None,
    volume_lookup: Optional[Callable[[str, str], float]] = None,
    floating_ip_lookup: Optional[Callable[[str], float]] = None,
    gpu_hourly: Optional[float] = None,
    compute_hourly: Optional[float] = None,
    warnings: Optional[List[str]] = None,
) -> RunCost:
    overrides = overrides if overrides is not None else load_overrides()
    priced: List[ResourceCost] = []
    warn = list(warnings or [])
    rate_cache: Dict[str, Optional[float]] = {}
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
        extra_gpu = gpu_hourly if usage.resource_type == "gpu" else None
        extra_compute = compute_hourly if usage.resource_type == "vm" else None
        # When GPU is split, do not double-count GPU in the VSI line:
        vm_instance_cost = instance_cost
        if usage.resource_type == "vm" and extra_compute is None and gpu_hourly:
            # instance_cost includes GPU; subtract if we emit a GPU line.
            if instance_cost is not None:
                vm_instance_cost = max(0.0, instance_cost - gpu_hourly)
        rate, source, currency = resolve_rate(
            usage.resource_type,
            usage.sku,
            usage.region,
            overrides=overrides,
            instance_cost=vm_instance_cost if usage.resource_type == "vm" else None,
            catalog_lookup=catalog_lookup,
            volume_lookup=volume_lookup,
            floating_ip_lookup=floating_ip_lookup,
            gpu_hourly=extra_gpu,
            compute_hourly=extra_compute,
            rate_cache=rate_cache,
        )
        if rate is None:
            warn.append(
                f"{usage.resource_name}: no {usage.resource_type} rate for "
                f"sku={usage.sku} region={usage.region}"
            )
        priced.append(
            calculate_resource_cost(usage, rate, source, currency=currency)
        )

    known = [r.total_cost for r in priced if r.total_cost is not None]
    total = sum(known) if known else None
    hours = hours_from_seconds(header["runtime_seconds"])
    avg = (total / hours) if total is not None and hours > 0 else None
    # 24h equivalent uses the same mix of live resources, not IBM daily SKUs.
    est24 = None
    if header["runtime_seconds"] > 0 and total is not None:
        est24 = total / hours * 24.0 if hours else None

    categories = {"vm": 0.0, "gpu": 0.0, "storage": 0.0, "network": 0.0, "other": 0.0}
    for row in priced:
        rtype = row.usage.resource_type
        if rtype == "not_billed":
            # Explicit $0 — VPC/subnet/SG/rules/SSH keys from this run.
            categories["other"] += 0.0
            continue
        if row.total_cost is None:
            continue
        if rtype == "vm":
            categories["vm"] += row.total_cost
        elif rtype == "gpu":
            categories["gpu"] += row.total_cost
        elif rtype == "volume":
            categories["storage"] += row.total_cost
        elif rtype == "floating_ip":
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


def apply_shared_attribution(runs: List[RunCost]) -> List[RunCost]:
    """
    If the same resource_id is billed in two runs with overlapping windows,
    scale each run's cost by overlap / resource_runtime.
    Exclusive Zathras IBM runs never overlap; this protects terminate=0 reuse.
    """
    by_id: Dict[str, List[Tuple[int, ResourceCost]]] = {}
    for i, run in enumerate(runs):
        for rc in run.resources:
            by_id.setdefault(rc.usage.resource_id, []).append((i, rc))
    for _rid, items in by_id.items():
        if len(items) < 2:
            continue
        for i, rc in items:
            if rc.usage.start_time is None or rc.usage.end_time is None:
                continue
            if rc.total_cost is None:
                continue
            others = 0
            for j, other in items:
                if i == j:
                    continue
                if other.usage.start_time is None or other.usage.end_time is None:
                    continue
                others += overlap_seconds(
                    rc.usage.start_time,
                    rc.usage.end_time,
                    other.usage.start_time,
                    other.usage.end_time,
                )
            own = rc.usage.runtime_seconds or 0
            if own <= 0 or others <= 0:
                continue
            # Charge this run only for its exclusive+shared slice:
            # shared seconds are split equally among overlapping runs.
            share = own / (own + others) if (own + others) else 1.0
            rc.total_cost = rc.total_cost * share
            rc.usage.attribution = "time_overlap"
            rc.calculation += f"; shared-resource factor {share:.6f}"
    # Re-total
    for run in runs:
        known = [r.total_cost for r in run.resources if r.total_cost is not None]
        run.total_cost = sum(known) if known else None
        hours = hours_from_seconds(run.runtime_seconds)
        run.average_cost_per_hour = (
            run.total_cost / hours if run.total_cost is not None and hours > 0 else None
        )
    return runs


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
        "gpu": "gpu",
        "volume": "volume",
        "floating_ip": "fip",
        "not_billed": "other",
    }.get(resource_type, resource_type[:8])


def _cli_short_name(name: str, width: int = 40) -> str:
    if len(name) <= width:
        return name
    if width <= 1:
        return name[:width]
    return name[: width - 1] + "…"


def _cli_what_ran(run: RunCost) -> str:
    """One-line inventory summary for the TL;DR block."""
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
    order = ("vm", "gpu", "volume", "fip")
    for key in order:
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
        elif key == "fip":
            parts.append(f"{n} floating IP" if n == 1 else f"{n} floating IPs")
        elif key == "gpu":
            parts.append(f"{n} GPU" if n == 1 else f"{n} GPUs")
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
        f"  GPU        {_fmt_money(cat.get('gpu'))}",
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
        f"{'TYPE':<8} {'NAME':<40} {'SKU':<16} {'RUNTIME':<12} {'RATE/HR':<12} {'COST':>10}",
        "-" * 102,
    ]
    for row in billable:
        rate = (
            _fmt_money(row.hourly_rate) + "/hr"
            if row.hourly_rate is not None
            else "n/a"
        )
        cost = _fmt_money(row.total_cost)
        sku = (row.usage.sku or "-")[:16]
        lines.append(
            f"{_cli_type_label(row.usage.resource_type):<8} "
            f"{_cli_short_name(row.usage.resource_name, 40):<40} "
            f"{sku:<16} "
            f"{_fmt_hours(row.usage.runtime_seconds):<12} "
            f"{rate:<12} {cost:>10}"
        )
    lines.append("-" * 102)
    lines.extend(
        [
            f"TOTAL COST    : {_fmt_money(run.total_cost)} {run.currency}",
            f"Average cost/hour (total / run runtime): {_fmt_money(run.average_cost_per_hour)}",
            "This is not the sum of resource hourly rates when lifetimes differ.",
            f"Estimated 24-hour cost (not an IBM daily SKU): {_fmt_money(run.estimated_24h_cost)}",
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
        "start_time": run.start_time,
        "end_time": run.end_time,
        "runtime_seconds": run.runtime_seconds,
        "runtime_hours": hours_from_seconds(run.runtime_seconds),
        "runtime_source": run.runtime_source,
        "status": run.status,
        "currency": run.currency,
        "resources": resources,
        "category_totals": run.category_totals,
        "total_cost": run.total_cost,
        "average_cost_per_hour": run.average_cost_per_hour,
        "estimated_24h_cost": run.estimated_24h_cost,
        "warnings": run.warnings,
    }


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS zathras_run (
            run_id TEXT PRIMARY KEY,
            start_time INTEGER,
            end_time INTEGER,
            runtime_seconds INTEGER,
            status TEXT,
            total_cost REAL,
            currency TEXT,
            created_at INTEGER
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
            start_time INTEGER,
            end_time INTEGER,
            runtime_seconds INTEGER,
            hourly_rate REAL,
            daily_rate REAL,
            total_cost REAL,
            currency TEXT,
            pricing_source TEXT,
            calculation TEXT
        );
        CREATE TABLE IF NOT EXISTS pricing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT,
            service TEXT,
            resource_type TEXT,
            sku TEXT,
            region TEXT,
            unit TEXT,
            hourly_rate REAL,
            currency TEXT,
            effective_from INTEGER,
            effective_to INTEGER,
            source TEXT
        );
        """
    )


def persist(run: RunCost, db_path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        ensure_schema(conn)
        conn.execute("DELETE FROM run_resource WHERE run_id = ?", (run.run_id,))
        conn.execute(
            """
            INSERT OR REPLACE INTO zathras_run
            (run_id, start_time, end_time, runtime_seconds, status, total_cost, currency, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                run.start_time,
                run.end_time,
                run.runtime_seconds,
                run.status,
                run.total_cost,
                run.currency,
                int(datetime.now(tz=timezone.utc).timestamp()),
            ),
        )
        now = int(datetime.now(tz=timezone.utc).timestamp())
        for row in run.resources:
            u = row.usage
            conn.execute(
                """
                INSERT INTO run_resource (
                    run_id, resource_id, resource_type, resource_name, sku, region,
                    quantity, start_time, end_time, runtime_seconds, hourly_rate,
                    daily_rate, total_cost, currency, pricing_source, calculation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    u.resource_id,
                    u.resource_type,
                    u.resource_name,
                    u.sku,
                    u.region,
                    u.quantity,
                    u.start_time,
                    u.end_time,
                    u.runtime_seconds,
                    row.hourly_rate,
                    row.daily_rate,
                    row.total_cost,
                    row.currency,
                    row.pricing_source,
                    row.calculation,
                ),
            )
            if row.hourly_rate is not None:
                conn.execute(
                    """
                    INSERT INTO pricing (
                        provider, service, resource_type, sku, region, unit,
                        hourly_rate, currency, effective_from, effective_to, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "ibm",
                        "vpc",
                        u.resource_type,
                        u.sku,
                        u.region,
                        u.unit,
                        row.hourly_rate,
                        row.currency,
                        now,
                        None,
                        row.pricing_source,
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
    catalog_lookup: Optional[Callable[[str, str], float]] = None,
    volume_lookup: Any = _LOOKUP_DEFAULT,
    floating_ip_lookup: Any = _LOOKUP_DEFAULT,
    gpu_hourly: Optional[float] = None,
    compute_hourly: Optional[float] = None,
    use_catalog: bool = False,
) -> RunCost:
    header, usages, warnings = discover_ibm_resources(
        run_dir, configured_runtime_seconds=configured_runtime_seconds
    )
    overrides = load_overrides(overrides_path)
    instance_cost = _instance_cost_file(run_dir)
    # Storage + floating IP are never in instance_cost. Default to catalog
    # lookups; pass volume_lookup=None / floating_ip_lookup=None to disable
    # (offline unit tests).
    if volume_lookup is _LOOKUP_DEFAULT:
        volume_lookup = lookup_volume_gb_hour_price
    if floating_ip_lookup is _LOOKUP_DEFAULT:
        floating_ip_lookup = lookup_floating_ip_hourly_price
    lookup = catalog_lookup
    if use_catalog and lookup is None:
        lookup = lookup_hourly_price
    return price_run(
        header,
        usages,
        overrides=overrides,
        instance_cost=instance_cost,
        catalog_lookup=lookup,
        volume_lookup=volume_lookup,
        floating_ip_lookup=floating_ip_lookup,
        gpu_hourly=gpu_hourly,
        compute_hourly=compute_hourly,
        warnings=warnings,
    )


def find_latest_ibm_run(root: str) -> Optional[str]:
    latest: Optional[Tuple[float, str]] = None
    for dirpath, _dirnames, filenames in os.walk(root):
        if "ansible_vars_main.yml" not in filenames:
            continue
        info = parse_config_info(os.path.join(dirpath, "ansible_vars_main.yml"))
        if info.get("system_type") != "ibm":
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
    """Copy cost reports into results zip/tar. Never raises to the caller."""
    reports = [
        os.path.join(run_dir, "cost_report.json"),
        os.path.join(run_dir, "cost_report.txt"),
    ]
    reports = [p for p in reports if os.path.isfile(p)]
    if not reports:
        return
    try:
        tar_path = os.path.join(run_dir, "ibm_cost.tar")
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
        description="Calculate IBM Cloud cost for a Zathras run"
    )
    parser.add_argument("run_dir", nargs="?", help="Zathras run directory")
    parser.add_argument("--latest", action="store_true", help="Use newest IBM run under cwd")
    parser.add_argument("--json", action="store_true", help="Print JSON (API-shaped) output")
    parser.add_argument("--record", action="store_true", help="Write cost_report.json and sqlite")
    parser.add_argument(
        "--db",
        default="",
        help="SQLite path (default: <run_dir>/../../zathras_cost.db or ./zathras_cost.db)",
    )
    parser.add_argument("--overrides", default="", help="Pricing override file")
    parser.add_argument(
        "--configured-runtime-seconds",
        type=int,
        default=None,
        help="Level-3 runtime estimate when timestamps are missing",
    )
    parser.add_argument(
        "--use-catalog",
        action="store_true",
        help="Query IBM Global Catalog if instance_cost is missing",
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
        run_dir = find_latest_ibm_run(os.getcwd())
        if not run_dir:
            return _fail("no IBM Zathras run directories found")
    if not run_dir:
        parser.error("run_dir is required unless --latest is set")
    if not os.path.isdir(run_dir):
        return _fail(f"not a directory: {run_dir}")

    try:
        run = cost_run_dir(
            run_dir,
            overrides_path=args.overrides or None,
            configured_runtime_seconds=args.configured_runtime_seconds,
            use_catalog=args.use_catalog,
        )
    except Exception as exc:  # noqa: BLE001 - plugin must not crash the runner
        return _fail(str(exc))

    payload = run_to_json(run)
    if args.record:
        try:
            report_path = os.path.join(run_dir, "cost_report.json")
            with open(report_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
                fh.write("\n")
            text_path = os.path.join(run_dir, "cost_report.txt")
            with open(text_path, "w", encoding="utf-8") as fh:
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
