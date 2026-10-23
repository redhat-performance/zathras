#!/usr/bin/env python3
#
# Resolve Azure retail prices via the public Retail Prices API.
# https://prices.azure.com/api/retail/prices
#
# No Azure login required. Rates are never hard-coded here.
# Used by burden (instance_cost) and azure_cost.py.
#

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

RETAIL_API = "https://prices.azure.com/api/retail/prices"
DEFAULT_TIMEOUT = 30
# Azure common proration: 365/12 * 24
HOURS_PER_MONTH = (365.0 / 12.0) * 24.0

# Premium SSD managed-disk size → P-tier (smallest tier that fits).
# Source: Azure managed disk documentation (provisioned sizes).
_PREMIUM_SSD_TIERS: List[Tuple[int, str]] = [
    (4, "P1"),
    (8, "P2"),
    (16, "P3"),
    (32, "P4"),
    (64, "P6"),
    (128, "P10"),
    (256, "P15"),
    (512, "P20"),
    (1024, "P30"),
    (2048, "P40"),
    (4096, "P50"),
    (8192, "P60"),
    (16384, "P70"),
    (32767, "P80"),
]

FetchFn = Callable[[str, int], Dict[str, Any]]


class AzurePriceError(Exception):
    """Pricing lookup failed."""


def _get_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "curl/8.0.0 zathras-azure-instance-price",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise AzurePriceError(f"HTTP {exc.code} for {url}: {body}") from exc
    except Exception as exc:  # noqa: BLE001
        raise AzurePriceError(f"Request failed for {url}: {exc}") from exc


def _retail_items(
    odata_filter: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    fetch: Optional[FetchFn] = None,
    max_pages: int = 20,
) -> List[Dict[str, Any]]:
    fetch = fetch or _get_json
    params = urllib.parse.urlencode({"$filter": odata_filter})
    url: Optional[str] = f"{RETAIL_API}?{params}"
    items: List[Dict[str, Any]] = []
    pages = 0
    while url and pages < max_pages:
        doc = fetch(url, timeout)
        items.extend(doc.get("Items") or [])
        url = doc.get("NextPageLink") or doc.get("nextPageLink")
        pages += 1
    return items


def premium_ssd_tier(size_gb: int) -> str:
    if size_gb <= 0:
        raise AzurePriceError(f"disk size must be > 0, got {size_gb}")
    for max_gb, tier in _PREMIUM_SSD_TIERS:
        if size_gb <= max_gb:
            return tier
    return _PREMIUM_SSD_TIERS[-1][1]


def monthly_to_hourly(monthly: float) -> float:
    return float(monthly) / HOURS_PER_MONTH


def _is_linux_vm_item(item: Dict[str, Any]) -> bool:
    product = (item.get("productName") or "").lower()
    if "windows" in product:
        return False
    return True


def _is_spot_item(item: Dict[str, Any]) -> bool:
    meter = (item.get("meterName") or "").lower()
    sku = (item.get("skuName") or "").lower()
    return "spot" in meter or "spot" in sku


def _pick_vm_item(items: List[Dict[str, Any]], *, spot: bool) -> Dict[str, Any]:
    candidates = []
    for item in items:
        if (item.get("type") or "") not in ("Consumption", "DevTestConsumption"):
            continue
        if item.get("type") == "Reservation":
            continue
        if not _is_linux_vm_item(item):
            continue
        is_spot = _is_spot_item(item)
        if spot and not is_spot:
            continue
        if not spot and is_spot:
            continue
        uom = (item.get("unitOfMeasure") or "").lower()
        if "hour" not in uom:
            continue
        candidates.append(item)
    if not candidates:
        kind = "Spot" if spot else "OnDemand Linux"
        raise AzurePriceError(f"no {kind} Virtual Machines Consumption meter matched")
    # Prefer primary meter region and lowest price (stable).
    candidates.sort(
        key=lambda i: (
            0 if i.get("isPrimaryMeterRegion") else 1,
            float(i.get("retailPrice") or i.get("unitPrice") or 0),
        )
    )
    return candidates[0]


def lookup_vm_hourly_price(
    arm_sku: str,
    region: str,
    *,
    spot: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    fetch: Optional[FetchFn] = None,
) -> float:
    """USD per hour for a Linux VM SKU in an ARM region."""
    if not arm_sku or not region:
        raise AzurePriceError("arm_sku and region are required")
    odata = (
        f"serviceName eq 'Virtual Machines' and "
        f"armRegionName eq '{region}' and "
        f"armSkuName eq '{arm_sku}' and "
        f"priceType eq 'Consumption'"
    )
    items = _retail_items(odata, timeout=timeout, fetch=fetch)
    if not items:
        raise AzurePriceError(
            f"no Retail Prices for VM {arm_sku!r} in {region!r}"
        )
    chosen = _pick_vm_item(items, spot=spot)
    price = chosen.get("retailPrice")
    if price is None:
        price = chosen.get("unitPrice")
    if price is None:
        raise AzurePriceError(f"meter missing retailPrice for {arm_sku}")
    return float(price)


def _disk_product_filters(storage_account_type: str) -> List[str]:
    sat = (storage_account_type or "").upper()
    if sat in ("PREMIUM_LRS", "PREMIUMV2_LRS"):
        return ["Premium SSD", "Premium SSD Managed Disks"]
    if sat in ("STANDARDSSD_LRS", "STANDARDSSD_ZRS"):
        return ["Standard SSD", "Standard SSD Managed Disks"]
    if sat in ("STANDARD_LRS",):
        return ["Standard HDD", "Standard HDD Managed Disks"]
    if sat in ("ULTRASSD_LRS",):
        return ["Ultra Disks", "Ultra Disk"]
    return [storage_account_type]


def lookup_managed_disk_monthly_price(
    storage_account_type: str,
    region: str,
    size_gb: int,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    fetch: Optional[FetchFn] = None,
) -> Tuple[float, str]:
    """
    Return (monthly_usd_for_one_disk, audit_note).

    Premium SSD uses provisioned P-tiers (not invented GB rates).
    Other types use a matching Retail meter when found.
    """
    if size_gb <= 0:
        raise AzurePriceError("size_gb required for managed disk pricing")
    sat = storage_account_type or "Premium_LRS"
    products = _disk_product_filters(sat)

    if sat.upper() in ("PREMIUM_LRS", "PREMIUMV2_LRS"):
        tier = premium_ssd_tier(size_gb)
        # Meter names look like "P10 LRS Disk"
        odata = (
            f"serviceName eq 'Storage' and "
            f"armRegionName eq '{region}' and "
            f"priceType eq 'Consumption' and "
            f"contains(meterName, '{tier}')"
        )
        items = _retail_items(odata, timeout=timeout, fetch=fetch)
        matched = []
        for item in items:
            product = item.get("productName") or ""
            meter = item.get("meterName") or ""
            if not any(p.lower() in product.lower() for p in products):
                # Still accept clear Premium SSD P-tier meters.
                if "premium" not in product.lower() and "managed disk" not in product.lower():
                    continue
            if tier.lower() not in meter.lower():
                continue
            if "snapshot" in meter.lower() or "mount" in meter.lower():
                continue
            uom = (item.get("unitOfMeasure") or "").lower()
            if "month" not in uom and "/month" not in uom and uom not in ("1/month", "1 month"):
                # Some return "1/Month"
                if "month" not in uom:
                    continue
            matched.append(item)
        if not matched:
            raise AzurePriceError(
                f"no Premium SSD meter for tier {tier} size={size_gb}GB in {region}"
            )
        matched.sort(
            key=lambda i: (
                0 if i.get("isPrimaryMeterRegion") else 1,
                float(i.get("retailPrice") or 0),
            )
        )
        monthly = float(matched[0]["retailPrice"])
        note = (
            f"Premium SSD tier {tier} for {size_gb}GB; "
            f"meter={matched[0].get('meterName')}; "
            f"${monthly}/month → ${monthly_to_hourly(monthly):.6f}/hour "
            f"(÷ {HOURS_PER_MONTH:.4f} h/month)"
        )
        return monthly, note

    # Generic: find a GB/Month managed-disk meter for the product family.
    odata = (
        f"serviceName eq 'Storage' and "
        f"armRegionName eq '{region}' and "
        f"priceType eq 'Consumption'"
    )
    items = _retail_items(odata, timeout=timeout, fetch=fetch)
    matched = []
    for item in items:
        product = (item.get("productName") or "").lower()
        if not any(p.lower() in product for p in products):
            continue
        meter = (item.get("meterName") or "").lower()
        if "snapshot" in meter or "mount" in meter or "operations" in meter:
            continue
        uom = (item.get("unitOfMeasure") or "").lower()
        if "gb" in uom and "month" in uom:
            matched.append(item)
        elif "month" in uom and sat.upper() in ("STANDARD_LRS", "STANDARDSSD_LRS"):
            # Tiered standard disks — treat like premium if size token present.
            matched.append(item)
    if not matched:
        raise AzurePriceError(
            f"no managed disk meter for {sat!r} in {region!r} size={size_gb}"
        )
    matched.sort(
        key=lambda i: (
            0 if i.get("isPrimaryMeterRegion") else 1,
            float(i.get("retailPrice") or 0),
        )
    )
    chosen = matched[0]
    unit_price = float(chosen.get("retailPrice") or 0)
    uom = (chosen.get("unitOfMeasure") or "").lower()
    if "gb" in uom:
        monthly = unit_price * float(size_gb)
        note = (
            f"{sat} {size_gb}GB × ${unit_price}/GB-month "
            f"(meter={chosen.get('meterName')}) = ${monthly}/month → "
            f"${monthly_to_hourly(monthly):.6f}/hour"
        )
    else:
        monthly = unit_price
        note = (
            f"{sat} disk meter={chosen.get('meterName')}; "
            f"${monthly}/month → ${monthly_to_hourly(monthly):.6f}/hour"
        )
    return monthly, note


def lookup_managed_disk_hourly_price(
    storage_account_type: str,
    region: str,
    size_gb: int,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    fetch: Optional[FetchFn] = None,
) -> float:
    monthly, _note = lookup_managed_disk_monthly_price(
        storage_account_type, region, size_gb, timeout=timeout, fetch=fetch
    )
    return monthly_to_hourly(monthly)


def lookup_public_ip_hourly_price(
    region: str,
    *,
    sku: str = "Basic",
    timeout: int = DEFAULT_TIMEOUT,
    fetch: Optional[FetchFn] = None,
) -> float:
    """USD per hour for a public IP (Basic Dynamic / Standard)."""
    if not region:
        raise AzurePriceError("region is required")
    odata = (
        f"serviceName eq 'Virtual Network' and "
        f"armRegionName eq '{region}' and "
        f"priceType eq 'Consumption'"
    )
    items = _retail_items(odata, timeout=timeout, fetch=fetch)
    sku_l = (sku or "Basic").lower()
    matched = []
    for item in items:
        product = (item.get("productName") or "").lower()
        meter = (item.get("meterName") or "").lower()
        sku_name = (item.get("skuName") or "").lower()
        blob = f"{product} {meter} {sku_name}"
        if "ip" not in blob and "public ip" not in blob:
            continue
        if "prefix" in blob:
            continue
        if sku_l == "basic" and "basic" not in blob:
            continue
        if sku_l == "standard" and "standard" not in blob:
            continue
        # Prefer dynamic for Basic (matches azurerm_public_ip allocation_method).
        uom = (item.get("unitOfMeasure") or "").lower()
        if "hour" not in uom:
            continue
        matched.append(item)
    if not matched:
        raise AzurePriceError(
            f"no public IP meter for sku={sku!r} in {region!r}"
        )
    # Prefer "Public IP" + Dynamic when Basic.
    def _score(i: Dict[str, Any]) -> Tuple[int, int, float]:
        meter = (i.get("meterName") or "").lower()
        primary = 0 if i.get("isPrimaryMeterRegion") else 1
        dyn = 0 if "dynamic" in meter else 1
        return (primary, dyn, float(i.get("retailPrice") or 0))

    matched.sort(key=_score)
    return float(matched[0]["retailPrice"])


def daily_from_hourly(hourly: float) -> float:
    return float(hourly) * 24.0


def _format_price(price: float) -> str:
    return f"{price:.6f}".rstrip("0").rstrip(".") if "." in f"{price:.6f}" else str(price)


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Look up Azure Retail Prices for a VM SKU / region"
    )
    parser.add_argument("sku", nargs="?", help="ARM SKU, e.g. Standard_D2s_v3")
    parser.add_argument("region", nargs="?", help="ARM region, e.g. eastus")
    parser.add_argument(
        "--hourly-only",
        action="store_true",
        help="Print only the hourly USD number (for burden instance_cost)",
    )
    parser.add_argument(
        "--spot",
        action="store_true",
        help="Select Spot Consumption meter instead of OnDemand Linux",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"HTTP timeout seconds (default {DEFAULT_TIMEOUT})",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not args.sku or not args.region:
        parser.error("sku and region are required")
    try:
        price = lookup_vm_hourly_price(
            args.sku, args.region, spot=args.spot, timeout=args.timeout
        )
    except AzurePriceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.hourly_only:
        print(_format_price(price))
    else:
        print(
            f"{args.sku} {args.region}: ${_format_price(price)}/hour "
            f"(${_format_price(daily_from_hourly(price))}/day estimate)"
            + (" [spot]" if args.spot else "")
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
