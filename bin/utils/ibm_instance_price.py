#!/usr/bin/env python3
#
# Resolve an estimated IBM Cloud VPC on-demand hourly price for a
# profile/region pair using the public Global Catalog pricing API.
#
# Mirrors the AWS burden path (ec2.shop -> gl_base_cost -> instance_cost):
# print a single hourly USD number on stdout for kick_off.sh report_usage.
#
# Formula used by kick_off.sh (unchanged):
#   cost = (benchmark_seconds * hourly_price) / 3600
#
# Daily estimate (display / --price-all only; not used by kick_off.sh):
#   daily = hourly_price * 24
#
# Hourly price resolution (multi-tenant / on-demand):
#   1) Gen2-style: part-is.cpu-hours + part-is.ram-hours
#      (+ GPU hours when present, e.g. part-is.v100-hours)
#   2) Gen3/Gen4/Flex-style: INSTANCE_HOURS_MULTI_TENANT
#      (part-is.instance-hours-<profile>)
#
# Deployment name variants tried under the profile's plan:
#   <profile>-<region>
#   <profile>-<region>-rc
#
# OS license metrics (RHEL/Windows/etc.) are excluded to match CPT BYOL
# images and the AWS Linux (non-RHEL) estimate from ec2.shop.
#
# Known profile names (from IBM VPC docs) live in:
#   config/ibm_vpc_profiles.cfg
#

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Tuple

CATALOG = "https://globalcatalog.cloud.ibm.com/api/v1"
CPU_METRIC = "part-is.cpu-hours"
RAM_METRIC = "part-is.ram-hours"
MULTI_TENANT_UNIT = "INSTANCE_HOURS_MULTI_TENANT"
DEFAULT_TIMEOUT = 30

# OS / software license metrics to never include in the estimate.
_OS_LICENSE_PREFIXES = (
    "part-is.redhat",
    "part-is.rhel",
    "part-is.windows",
    "part-is.suse",
    "part-is.CentOS",
    "part-is.Debian",
    "part-is.Ubuntu",
    "part-is.Rocky",
    "part-is.Fedora",
    "part-is.SW.",
)


class IbmPriceError(Exception):
    """Pricing lookup failed."""


def _profiles_cfg_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "config", "ibm_vpc_profiles.cfg"))


def load_known_profiles(path: Optional[str] = None) -> List[str]:
    cfg = path or _profiles_cfg_path()
    if not os.path.isfile(cfg):
        raise IbmPriceError(f"Known profiles file not found: {cfg}")
    profiles: List[str] = []
    with open(cfg, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            profiles.append(line)
    return profiles


def _get_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    # Cloudflare blocks urllib's default User-Agent (Error 1010). Use a
    # curl-like agent so public Global Catalog pricing stays reachable.
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "curl/8.0.0 zathras-ibm-instance-price",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise IbmPriceError(f"HTTP {exc.code} for {url}: {body}") from exc
    except Exception as exc:  # noqa: BLE001 - surface network/parse failures
        raise IbmPriceError(f"Request failed for {url}: {exc}") from exc


def _multi_tenant_plan(profile_doc: Dict[str, Any]) -> str:
    try:
        measures = profile_doc["metadata"]["other"]["profile"]["measures"]
    except (KeyError, TypeError) as exc:
        raise IbmPriceError("Profile document missing measures metadata") from exc

    for measure in measures:
        if measure.get("component") != "instance":
            continue
        for deployment in measure.get("deployments") or []:
            if deployment.get("type") == "multi-tenant" and deployment.get("plan"):
                return deployment["plan"]
        for deployment in measure.get("deployments") or []:
            if deployment.get("plan"):
                return deployment["plan"]
    raise IbmPriceError("No instance plan found in profile measures")


def _find_deployment_id(plan_id: str, profile: str, region: str) -> str:
    """
    Gen2 deployments are named <profile>-<region>.
    Gen3/Gen4/Flex deployments are often named <profile>-<region>-rc.
    """
    candidates = [f"{profile}-{region}", f"{profile}-{region}-rc"]
    query = urllib.parse.urlencode({"q": f"{profile}-{region}", "limit": 50})
    url = f"{CATALOG}/{urllib.parse.quote(plan_id, safe='')}/*?{query}"
    doc = _get_json(url)
    resources = doc.get("resources") or []
    by_name = {r.get("name"): r.get("id") for r in resources if r.get("name") and r.get("id")}

    for want in candidates:
        if want in by_name:
            return by_name[want]

    # Fallback: first resource whose name starts with profile-region.
    prefix = f"{profile}-{region}"
    for name, dep_id in by_name.items():
        if name.startswith(prefix):
            return dep_id

    raise IbmPriceError(
        f"No catalog deployment for {profile!r} in {region!r} under plan {plan_id} "
        f"(tried {candidates})"
    )


def _usa_usd_unit_price(metric: Dict[str, Any]) -> Optional[float]:
    for amount in metric.get("amounts") or []:
        if amount.get("country") == "USA" and amount.get("currency") == "USD":
            prices = amount.get("prices") or []
            if not prices:
                continue
            return float(prices[0]["price"])
    return None


def _is_os_license_metric(metric_id: str) -> bool:
    return any(metric_id.startswith(p) for p in _OS_LICENSE_PREFIXES)


def _is_gpu_metric(metric_id: str, charge_unit_name: str) -> bool:
    mid = (metric_id or "").lower()
    cun = (charge_unit_name or "").upper()
    if _is_os_license_metric(metric_id):
        return False
    if mid in (CPU_METRIC, RAM_METRIC):
        return False
    if "gpu" in mid or mid.endswith("-hours") and any(
        g in mid
        for g in (
            "v100",
            "a100",
            "h100",
            "h200",
            "l4",
            "l40",
            "gaudi",
            "b300",
            "t4",
        )
    ):
        return True
    if "GPU" in cun and "HOUR" in cun:
        return True
    return False


def compute_metric_parts(pricing_doc: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """
    Split catalog metrics into cpu, ram, gpu, and bundled multi-tenant hours.

    OS license metrics are ignored (BYOL / CPT images).
    """
    metrics = pricing_doc.get("metrics") or []
    cpu = ram = None
    gpu_total = 0.0
    gpu_seen = False
    multi_tenant = None

    for metric in metrics:
        metric_id = metric.get("metric_id") or ""
        charge_unit_name = metric.get("charge_unit_name") or ""
        price = _usa_usd_unit_price(metric)
        if price is None:
            continue

        if metric_id == CPU_METRIC:
            cpu = price
        elif metric_id == RAM_METRIC:
            ram = price
        elif charge_unit_name == MULTI_TENANT_UNIT or (
            metric_id.startswith("part-is.instance-hours-")
            and "dh-" not in metric_id
            and "reservation" not in metric_id
        ):
            # Prefer the explicit MULTI_TENANT unit when several instance-hours
            # metrics exist (dedicated/reservation are ignored).
            if charge_unit_name == MULTI_TENANT_UNIT or multi_tenant is None:
                if charge_unit_name == MULTI_TENANT_UNIT:
                    multi_tenant = price
                elif multi_tenant is None and not _is_os_license_metric(metric_id):
                    multi_tenant = price
        elif _is_gpu_metric(metric_id, charge_unit_name):
            gpu_total += price
            gpu_seen = True

    return {
        "cpu": cpu,
        "ram": ram,
        "gpu": gpu_total if gpu_seen else None,
        "multi_tenant": multi_tenant,
    }


def hourly_price_from_pricing_doc(pricing_doc: Dict[str, Any]) -> float:
    """
    Prefer cpu+ram(+gpu) when those metrics exist (Gen2 / gx2).
    Otherwise use bundled INSTANCE_HOURS_MULTI_TENANT (Gen3/Gen4/Flex).
    """
    parts = compute_metric_parts(pricing_doc)
    gpu = parts["gpu"] or 0.0
    if parts["cpu"] is not None and parts["ram"] is not None:
        return parts["cpu"] + parts["ram"] + gpu
    if parts["multi_tenant"] is not None:
        return parts["multi_tenant"] + gpu
    raise IbmPriceError(
        "Pricing missing compute metrics "
        f"(need {CPU_METRIC}+{RAM_METRIC} or {MULTI_TENANT_UNIT})"
    )


def price_breakdown_from_pricing_doc(pricing_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Hourly USD split so GPU can be reported separately from the VSI."""
    parts = compute_metric_parts(pricing_doc)
    gpu = parts["gpu"] or 0.0
    if parts["cpu"] is not None and parts["ram"] is not None:
        compute = parts["cpu"] + parts["ram"]
        model = "cpu_ram_gpu" if gpu else "cpu_ram"
        calculation = (
            f"cpu {parts['cpu']} + ram {parts['ram']}"
            + (f" + gpu {gpu}" if gpu else "")
        )
    elif parts["multi_tenant"] is not None:
        compute = parts["multi_tenant"]
        model = "instance_hours_multi_tenant"
        calculation = f"instance_hours {compute}" + (f" + gpu {gpu}" if gpu else "")
    else:
        raise IbmPriceError(
            "Pricing missing compute metrics "
            f"(need {CPU_METRIC}+{RAM_METRIC} or {MULTI_TENANT_UNIT})"
        )
    hourly = compute + gpu
    return {
        "hourly": hourly,
        "compute_hourly": compute,
        "gpu_hourly": gpu,
        "cpu_hourly": parts["cpu"],
        "ram_hourly": parts["ram"],
        "model": model,
        "calculation": calculation,
        "currency": "USD",
        "unit": "INSTANCE_HOUR",
    }


def lookup_hourly_price(profile: str, region: str) -> float:
    profile = profile.strip()
    region = region.strip()
    if not profile:
        raise IbmPriceError("Empty IBM profile")
    if not region:
        raise IbmPriceError("Empty IBM region")

    profile_url = (
        f"{CATALOG}/{urllib.parse.quote(profile, safe='')}"
        f"?{urllib.parse.urlencode({'include': '*'})}"
    )
    profile_doc = _get_json(profile_url)
    if profile_doc.get("kind") != "instance.profile":
        raise IbmPriceError(
            f"{profile!r} is not an instance.profile "
            f"(kind={profile_doc.get('kind')!r})"
        )

    plan_id = _multi_tenant_plan(profile_doc)
    deployment_id = _find_deployment_id(plan_id, profile, region)
    pricing_url = (
        f"{CATALOG}/{urllib.parse.quote(deployment_id, safe='')}/pricing"
    )
    pricing_doc = _get_json(pricing_url)
    return hourly_price_from_pricing_doc(pricing_doc)


# Block Storage for VPC plan names under service is.volume
VOLUME_SERVICE = "is.volume"
VOLUME_PLAN_BY_PROFILE = {
    "general-purpose": "gen2-volume-general-purpose",
    "5iops-tier": "gen2-volume-5iops-tier",
    "10iops-tier": "gen2-volume-10iops-tier",
    "custom": "gen2-volume-custom",
    "sdp": "gen2-volume-sdp",
}
FLOATING_IP_SERVICE = "is.floating-ip"
FLOATING_IP_PLAN = "default-nextgen"


def _service_plan_id(service_id: str, plan_name: str) -> str:
    url = (
        f"{CATALOG}/{urllib.parse.quote(service_id, safe='')}/*"
        f"?{urllib.parse.urlencode({'limit': 50})}"
    )
    doc = _get_json(url)
    for resource in doc.get("resources") or []:
        if resource.get("kind") == "plan" and resource.get("name") == plan_name:
            rid = resource.get("id")
            if rid:
                return rid
    raise IbmPriceError(f"No plan {plan_name!r} under service {service_id}")


def _find_named_deployment(plan_id: str, candidates: List[str], region: str) -> str:
    query = urllib.parse.urlencode({"q": region, "limit": 50})
    url = f"{CATALOG}/{urllib.parse.quote(plan_id, safe='')}/*?{query}"
    doc = _get_json(url)
    by_name = {
        r.get("name"): r.get("id")
        for r in (doc.get("resources") or [])
        if r.get("name") and r.get("id") and r.get("kind") == "deployment"
    }
    for want in candidates:
        if want in by_name:
            return by_name[want]
    # Prefer non-beta deployments containing the region.
    for name, dep_id in by_name.items():
        if "beta" in name or "free" in name:
            continue
        if region in name:
            return dep_id
    raise IbmPriceError(
        f"No catalog deployment under plan {plan_id} for region {region!r} "
        f"(tried {candidates})"
    )


def _usa_usd_from_metrics(
    pricing_doc: Dict[str, Any],
    *,
    prefer_units: Tuple[str, ...],
    prefer_metric_substrings: Tuple[str, ...] = (),
) -> float:
    metrics = pricing_doc.get("metrics") or []
    for unit in prefer_units:
        for metric in metrics:
            if metric.get("charge_unit_name") != unit:
                continue
            mid = metric.get("metric_id") or ""
            if prefer_metric_substrings and not any(
                s in mid for s in prefer_metric_substrings
            ):
                continue
            price = _usa_usd_unit_price(metric)
            if price is not None:
                return price
    for metric in metrics:
        mid = metric.get("metric_id") or ""
        if prefer_metric_substrings and not any(
            s in mid for s in prefer_metric_substrings
        ):
            continue
        price = _usa_usd_unit_price(metric)
        if price is not None:
            return price
    raise IbmPriceError(
        f"Pricing missing metrics for units={prefer_units} "
        f"substrings={prefer_metric_substrings}"
    )


def lookup_volume_gb_hour_price(profile: str, region: str) -> float:
    """
    USD per GB-hour for a VPC Block Storage volume profile.

    Example: general-purpose in us-south → is.volume.generalpurpose.GB.
    """
    profile = (profile or "general-purpose").strip()
    region = region.strip()
    plan_name = VOLUME_PLAN_BY_PROFILE.get(profile)
    if not plan_name:
        raise IbmPriceError(
            f"Unsupported volume profile {profile!r}; "
            f"known: {sorted(VOLUME_PLAN_BY_PROFILE)}"
        )
    plan_id = _service_plan_id(VOLUME_SERVICE, plan_name)
    deployment_id = _find_named_deployment(
        plan_id,
        [f"{plan_name}-{region}", f"{plan_name}-{region}-rc"],
        region,
    )
    pricing_doc = _get_json(
        f"{CATALOG}/{urllib.parse.quote(deployment_id, safe='')}/pricing"
    )
    return _usa_usd_from_metrics(
        pricing_doc,
        prefer_units=("GIGABYTE_HOURS",),
        prefer_metric_substrings=(".GB", "gigabyte", "generalpurpose", "iops"),
    )


def lookup_floating_ip_hourly_price(region: str) -> float:
    """
    USD per floating-IP hour (catalog unit display: Instance-Hour).
    """
    region = region.strip()
    plan_id = _service_plan_id(FLOATING_IP_SERVICE, FLOATING_IP_PLAN)
    deployment_id = _find_named_deployment(
        plan_id,
        [
            f"{FLOATING_IP_PLAN}-{region}-rc",
            f"{FLOATING_IP_PLAN}-{region}-1-rc",
            f"{FLOATING_IP_PLAN}-{region}",
        ],
        region,
    )
    pricing_doc = _get_json(
        f"{CATALOG}/{urllib.parse.quote(deployment_id, safe='')}/pricing"
    )
    return _usa_usd_from_metrics(
        pricing_doc,
        prefer_units=("INSTANCES", "INSTANCE_HOURS"),
        prefer_metric_substrings=("floating-ip",),
    )


def _format_price(price: float) -> str:
    return f"{price:.6f}".rstrip("0").rstrip(".")


def daily_from_hourly(hourly: float) -> float:
    """On-demand estimate for 24 hours at the catalog hourly rate."""
    # Round hourly first so printed daily matches printed_hourly * 24.
    return round(round(hourly, 6) * 24.0, 6)


def _format_hourly_daily(hourly: float) -> str:
    """Tab-separated hourly and daily USD for machine-readable output."""
    hourly_r = round(hourly, 6)
    return f"{_format_price(hourly_r)}\t{_format_price(daily_from_hourly(hourly_r))}"


def _format_hourly_daily_human(hourly: float) -> str:
    hourly_r = round(hourly, 6)
    return (
        f"{_format_price(hourly_r)}/hour\t"
        f"{_format_price(daily_from_hourly(hourly_r))}/day"
    )


def _fixture_pricing_docs() -> List[Tuple[str, Dict[str, Any], float]]:
    """Offline fixtures covering Gen2 cpu+ram, Gen3 bundled, and GPU."""
    gen2 = {
        "metrics": [
            {
                "metric_id": CPU_METRIC,
                "amounts": [
                    {"country": "USA", "currency": "USD", "prices": [{"price": 0.443}]}
                ],
            },
            {
                "metric_id": RAM_METRIC,
                "amounts": [
                    {"country": "USA", "currency": "USD", "prices": [{"price": 0.36}]}
                ],
            },
            {
                "metric_id": "part-is.redhatOS",
                "amounts": [
                    {"country": "USA", "currency": "USD", "prices": [{"price": 0.017}]}
                ],
            },
        ]
    }
    gen3 = {
        "metrics": [
            {
                "metric_id": "part-is.instance-hours-bx3d-16x80",
                "charge_unit_name": MULTI_TENANT_UNIT,
                "amounts": [
                    {"country": "USA", "currency": "USD", "prices": [{"price": 0.907}]}
                ],
            },
            {
                "metric_id": "part-is.redhatOS",
                "amounts": [
                    {"country": "USA", "currency": "USD", "prices": [{"price": 0.017}]}
                ],
            },
        ]
    }
    gpu = {
        "metrics": [
            {
                "metric_id": CPU_METRIC,
                "amounts": [
                    {"country": "USA", "currency": "USD", "prices": [{"price": 0.237}]}
                ],
            },
            {
                "metric_id": RAM_METRIC,
                "amounts": [
                    {"country": "USA", "currency": "USD", "prices": [{"price": 0.282}]}
                ],
            },
            {
                "metric_id": "part-is.v100-hours",
                "charge_unit_name": "V100_HOURS",
                "amounts": [
                    {"country": "USA", "currency": "USD", "prices": [{"price": 2.09}]}
                ],
            },
        ]
    }
    return [
        ("gen2", gen2, 0.803),
        ("gen3", gen3, 0.907),
        ("gpu", gpu, 2.609),
    ]


def run_self_test() -> int:
    for name, doc, expected in _fixture_pricing_docs():
        price = hourly_price_from_pricing_doc(doc)
        if abs(price - expected) > 1e-9:
            print(
                f"SELFTEST FAIL ({name}): got {price}, expected {expected}",
                file=sys.stderr,
            )
            return 1
    try:
        profiles = load_known_profiles()
    except IbmPriceError as exc:
        print(f"SELFTEST FAIL: {exc}", file=sys.stderr)
        return 1
    if len(profiles) < 100:
        print(
            f"SELFTEST FAIL: expected many known profiles, got {len(profiles)}",
            file=sys.stderr,
        )
        return 1
    for required in ("bx2-16x64", "cx2-16x32", "mx2-16x128", "gx2-8x64x1v100", "bx3d-16x80"):
        if required not in profiles:
            print(f"SELFTEST FAIL: missing known profile {required}", file=sys.stderr)
            return 1
    if abs(daily_from_hourly(0.803) - 19.272) > 1e-9:
        print("SELFTEST FAIL: daily_from_hourly(0.803) != 19.272", file=sys.stderr)
        return 1
    gpu_break = price_breakdown_from_pricing_doc(_fixture_pricing_docs()[2][1])
    if abs(gpu_break["compute_hourly"] - 0.519) > 1e-9 or abs(gpu_break["gpu_hourly"] - 2.09) > 1e-9:
        print(f"SELFTEST FAIL: gpu breakdown {gpu_break}", file=sys.stderr)
        return 1
    vol_doc = {
        "metrics": [
            {
                "metric_id": "is.volume.generalpurpose.GB",
                "charge_unit_name": "GIGABYTE_HOURS",
                "amounts": [
                    {"country": "USA", "currency": "USD", "prices": [{"price": 0.00012025}]}
                ],
            }
        ]
    }
    fip_doc = {
        "metrics": [
            {
                "metric_id": "part-is.floating-ip-instance",
                "charge_unit_name": "INSTANCES",
                "amounts": [
                    {"country": "USA", "currency": "USD", "prices": [{"price": 0.006}]}
                ],
            }
        ]
    }
    if abs(_usa_usd_from_metrics(vol_doc, prefer_units=("GIGABYTE_HOURS",)) - 0.00012025) > 1e-12:
        print("SELFTEST FAIL: volume GB-hour fixture", file=sys.stderr)
        return 1
    if abs(_usa_usd_from_metrics(fip_doc, prefer_units=("INSTANCES",), prefer_metric_substrings=("floating-ip",)) - 0.006) > 1e-12:
        print("SELFTEST FAIL: floating IP fixture", file=sys.stderr)
        return 1
    # First field remains hourly so burden can parse it.
    print(_format_hourly_daily(0.803))
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Look up IBM VPC on-demand hourly and daily USD price"
    )
    parser.add_argument("profile", nargs="?", help="IBM instance profile, e.g. bx2-16x64")
    parser.add_argument(
        "region",
        nargs="?",
        help="IBM region, e.g. us-south (not zone)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run offline fixture tests",
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List known profiles from config/ibm_vpc_profiles.cfg",
    )
    parser.add_argument(
        "--price-all",
        metavar="REGION",
        help="Look up hourly and daily price for every known profile in REGION",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="With --price-all, keep going when a profile fails",
    )
    parser.add_argument(
        "--hourly-only",
        action="store_true",
        help="Print only the hourly USD price (used by burden instance_cost)",
    )
    parser.add_argument(
        "--human",
        action="store_true",
        help="Print hourly/day labels instead of bare numbers",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.self_test:
        return run_self_test()

    if args.list_profiles:
        try:
            for profile in load_known_profiles():
                print(profile)
        except IbmPriceError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.price_all:
        region = args.price_all
        failures = 0
        try:
            profiles = load_known_profiles()
        except IbmPriceError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print("profile\thourly_usd\tdaily_usd")
        for profile in profiles:
            try:
                price = lookup_hourly_price(profile, region)
                print(f"{profile}\t{_format_hourly_daily(price)}")
            except IbmPriceError as exc:
                failures += 1
                print(f"{profile}\tERROR\t{exc}", file=sys.stderr)
                if not args.continue_on_error:
                    return 1
        return 1 if failures else 0

    if not args.profile or not args.region:
        parser.error("profile and region are required unless using a flag mode")

    try:
        price = lookup_hourly_price(args.profile, args.region)
    except IbmPriceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.hourly_only:
        print(_format_price(price))
    elif args.human:
        print(_format_hourly_daily_human(price))
    else:
        print(_format_hourly_daily(price))
    return 0


if __name__ == "__main__":
    sys.exit(main())
