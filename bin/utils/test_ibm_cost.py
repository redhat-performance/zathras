#!/usr/bin/env python3
"""Unit tests for IBM Zathras cost tracking. No live IBM API calls."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest

UTILS = os.path.dirname(os.path.abspath(__file__))
if UTILS not in sys.path:
    sys.path.insert(0, UTILS)

import ibm_cost  # noqa: E402
from ibm_instance_price import (  # noqa: E402
    hourly_price_from_pricing_doc,
    price_breakdown_from_pricing_doc,
    daily_from_hourly,
)


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def _run_dir(tmp: str, **kwargs) -> str:
    path = os.path.join(tmp, kwargs.get("name", "bx2-16x64_0"))
    os.makedirs(path, exist_ok=True)
    sku = kwargs.get("sku", "bx2-16x64")
    region = kwargs.get("region", "us-south")
    disks = kwargs.get("disks", "none")
    networks = kwargs.get("networks", "0")
    run_label = kwargs.get("run_label", "alice_rhel")
    _write(
        os.path.join(path, "ansible_vars_main.yml"),
        (
            "---\n"
            "config_info:\n"
            f"  system_type: ibm\n"
            f"  host_or_cloud_inst: {sku}\n"
            f"  host_config: {sku}\n"
            f"  cloud_region: {region}\n"
            f"  cloud_zone: {region}-1\n"
            f"  run_label: {run_label}\n"
            f"  cloud_disks: {disks}\n"
            f"  cloud_numb_networks: {networks}\n"
        ),
    )
    if "instance_cost" in kwargs:
        _write(os.path.join(path, "instance_cost"), str(kwargs["instance_cost"]) + "\n")
    if "lifecycle" in kwargs:
        _write(os.path.join(path, "instance_lifecycle"), kwargs["lifecycle"])
    if "test_times" in kwargs:
        _write(os.path.join(path, "test_times"), kwargs["test_times"])
    if "meta" in kwargs:
        _write(os.path.join(path, "meta_data.yml"), kwargs["meta"])
    if kwargs.get("failed"):
        _write(os.path.join(path, "cpu_type_failure"), "1\n")
    if kwargs.get("returned", True):
        _write(os.path.join(path, "test_returned"), "Test completed\n")
    return path


class RuntimeTests(unittest.TestCase):
    def test_seconds_minutes_hours_fractional(self):
        self.assertEqual(ibm_cost.runtime_seconds(0, 1)[0], 1)
        self.assertEqual(ibm_cost.runtime_seconds(0, 60)[0], 60)
        self.assertEqual(ibm_cost.runtime_seconds(0, 3600)[0], 3600)
        self.assertAlmostEqual(ibm_cost.hours_from_seconds(16200), 4.5)

    def test_zero_runtime(self):
        self.assertEqual(ibm_cost.runtime_seconds(100, 100)[0], 0)
        cost = ibm_cost.calculate_resource_cost(
            ibm_cost.ResourceUsage(
                resource_id="x",
                resource_type="vm",
                resource_name="VM",
                sku="bx2-16x64",
                region="us-south",
                quantity=1,
                start_time=100,
                end_time=100,
                runtime_seconds=0,
                runtime_source="ibm_lifecycle",
                runtime_is_estimate=False,
                unit="INSTANCE_HOUR",
            ),
            10.5,
            "test",
        )
        self.assertEqual(cost.total_cost, 0.0)

    def test_missing_timestamps(self):
        seconds, note = ibm_cost.runtime_seconds(None, 10)
        self.assertEqual(seconds, 0)
        self.assertEqual(note, "missing_timestamps")
        with self.assertRaises(ibm_cost.CostError):
            ibm_cost.runtime_seconds(None, None, missing="error")

    def test_end_before_start(self):
        seconds, note = ibm_cost.runtime_seconds(50, 10)
        self.assertEqual(seconds, 0)
        self.assertEqual(note, "end_before_start")

    def test_overlap(self):
        # 10:00-12:00 vs 11:00-13:00 → 3600s
        self.assertEqual(ibm_cost.overlap_seconds(0, 7200, 3600, 10800), 3600)
        self.assertEqual(ibm_cost.overlap_seconds(0, 3600, 3600, 7200), 0)


class PricingTests(unittest.TestCase):
    def test_hourly_and_daily(self):
        self.assertAlmostEqual(daily_from_hourly(0.803), 19.272)
        usage = ibm_cost.ResourceUsage(
            resource_id="vm",
            resource_type="vm",
            resource_name="VM",
            sku="bx2-16x64",
            region="us-south",
            quantity=1,
            start_time=0,
            end_time=3600,
            runtime_seconds=3600,
            runtime_source="ibm_lifecycle",
            runtime_is_estimate=False,
            unit="INSTANCE_HOUR",
        )
        row = ibm_cost.calculate_resource_cost(usage, 10.5, "pricing_override")
        self.assertAlmostEqual(row.total_cost, 10.5)
        self.assertAlmostEqual(row.daily_rate, 252.0)

    def test_sku_and_region_overrides(self):
        rows = [
            {
                "resource_type": "vm",
                "sku": "bx2-16x64",
                "region": "us-south",
                "unit": "INSTANCE_HOUR",
                "hourly_rate": "1.5",
                "currency": "USD",
            },
            {
                "resource_type": "vm",
                "sku": "bx2-16x64",
                "region": "eu-de",
                "unit": "INSTANCE_HOUR",
                "hourly_rate": "1.7",
                "currency": "USD",
            },
        ]
        south = ibm_cost.override_rate(rows, "vm", "bx2-16x64", "us-south")
        eu = ibm_cost.override_rate(rows, "vm", "bx2-16x64", "eu-de")
        miss = ibm_cost.override_rate(rows, "vm", "cx2-16x32", "us-south")
        self.assertAlmostEqual(south[0], 1.5)
        self.assertAlmostEqual(eu[0], 1.7)
        self.assertIsNone(miss)

    def test_missing_pricing(self):
        usage = ibm_cost.ResourceUsage(
            resource_id="vm",
            resource_type="vm",
            resource_name="VM",
            sku="unknown",
            region="us-south",
            quantity=1,
            start_time=0,
            end_time=3600,
            runtime_seconds=3600,
            runtime_source="ibm_lifecycle",
            runtime_is_estimate=False,
            unit="INSTANCE_HOUR",
        )
        row = ibm_cost.calculate_resource_cost(usage, None, "unavailable")
        self.assertIsNone(row.total_cost)
        self.assertIn("unavailable", row.calculation)

    def test_changed_pricing_snapshot(self):
        usage = ibm_cost.ResourceUsage(
            resource_id="vm",
            resource_type="vm",
            resource_name="VM",
            sku="bx2-16x64",
            region="us-south",
            quantity=1,
            start_time=0,
            end_time=3600,
            runtime_seconds=3600,
            runtime_source="ibm_lifecycle",
            runtime_is_estimate=False,
            unit="INSTANCE_HOUR",
        )
        old = ibm_cost.calculate_resource_cost(usage, 1.0, "run_instance_cost")
        new = ibm_cost.calculate_resource_cost(usage, 2.0, "ibm_global_catalog")
        self.assertAlmostEqual(old.total_cost, 1.0)
        self.assertAlmostEqual(new.total_cost, 2.0)
        self.assertNotEqual(old.pricing_source, new.pricing_source)

    def test_catalog_fixtures(self):
        gen2 = {
            "metrics": [
                {
                    "metric_id": "part-is.cpu-hours",
                    "amounts": [
                        {"country": "USA", "currency": "USD", "prices": [{"price": 0.443}]}
                    ],
                },
                {
                    "metric_id": "part-is.ram-hours",
                    "amounts": [
                        {"country": "USA", "currency": "USD", "prices": [{"price": 0.36}]}
                    ],
                },
            ]
        }
        self.assertAlmostEqual(hourly_price_from_pricing_doc(gen2), 0.803)
        br = price_breakdown_from_pricing_doc(gen2)
        self.assertAlmostEqual(br["compute_hourly"], 0.803)
        self.assertAlmostEqual(br["gpu_hourly"], 0.0)


class CostScenarioTests(unittest.TestCase):
    def _price(self, tmp, **kwargs):
        overrides = kwargs.pop(
            "overrides",
            [
                {
                    "resource_type": "vm",
                    "sku": kwargs.get("sku", "bx2-16x64"),
                    "region": "us-south",
                    "unit": "INSTANCE_HOUR",
                    "hourly_rate": str(kwargs.pop("vm_rate", 10.5)),
                    "currency": "USD",
                }
            ],
        )
        extra_overrides = kwargs.pop("extra_overrides", [])
        run_dir = _run_dir(tmp, **kwargs)
        header, usages, warnings = ibm_cost.discover_ibm_resources(run_dir)
        return ibm_cost.price_run(
            header, usages, overrides=overrides + extra_overrides, warnings=warnings
        )

    def test_one_vm_one_hour(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._price(
                tmp,
                lifecycle="create_end_unix=0\nterminate_start_unix=3600\n",
            )
            vm = [r for r in run.resources if r.usage.resource_type == "vm"]
            self.assertEqual(len(vm), 1)
            self.assertAlmostEqual(vm[0].total_cost, 10.5)

    def test_one_vm_4_5_hours(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._price(
                tmp,
                lifecycle="create_end_unix=0\nterminate_start_unix=16200\n",
            )
            vm = [r for r in run.resources if r.usage.resource_type == "vm"][0]
            self.assertAlmostEqual(vm.total_cost, 10.5 * 4.5)

    def test_two_vms_four_hours(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._price(
                tmp,
                networks="1",
                lifecycle="create_end_unix=0\nterminate_start_unix=14400\n",
            )
            vms = [r for r in run.resources if r.usage.resource_type == "vm"]
            self.assertEqual(len(vms), 2)
            self.assertAlmostEqual(sum(v.total_cost for v in vms), 10.5 * 4 * 2)

    def test_vm_plus_gpu(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._price(
                tmp,
                sku="gx2-8x64x1v100",
                vm_rate=0.519,
                extra_overrides=[
                    {
                        "resource_type": "gpu",
                        "sku": "gx2-8x64x1v100",
                        "region": "us-south",
                        "unit": "GPU_HOUR",
                        "hourly_rate": "2.09",
                        "currency": "USD",
                    }
                ],
                lifecycle="create_end_unix=0\nterminate_start_unix=3600\n",
            )
            gpu = [r for r in run.resources if r.usage.resource_type == "gpu"]
            vm = [r for r in run.resources if r.usage.resource_type == "vm"]
            self.assertEqual(len(gpu), 1)
            self.assertAlmostEqual(gpu[0].total_cost, 2.09)
            self.assertAlmostEqual(vm[0].total_cost, 0.519)

    def test_vm_plus_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._price(
                tmp,
                disks="2:general-purpose:100:1",
                extra_overrides=[
                    {
                        "resource_type": "volume",
                        "sku": "general-purpose",
                        "region": "us-south",
                        "unit": "GB_HOUR",
                        "hourly_rate": "0.0001",
                        "currency": "USD",
                    }
                ],
                lifecycle="create_end_unix=0\nterminate_start_unix=3600\n",
            )
            data = [
                r
                for r in run.resources
                if r.usage.resource_type == "volume" and "data-volume" in r.usage.resource_name
            ]
            self.assertEqual(len(data), 2)
            # 100 GB * 1 hour * 0.0001 * 2 volumes
            self.assertAlmostEqual(sum(r.total_cost for r in data), 0.02)

    def test_storage_and_network_category_totals(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._price(
                tmp,
                lifecycle="create_end_unix=0\nterminate_start_unix=3600\n",
                extra_overrides=[
                    {
                        "resource_type": "volume",
                        "sku": "general-purpose",
                        "region": "us-south",
                        "unit": "GB_HOUR",
                        "hourly_rate": "0.00012025",
                        "currency": "USD",
                    },
                    {
                        "resource_type": "floating_ip",
                        "sku": "standard",
                        "region": "us-south",
                        "unit": "IP_HOUR",
                        "hourly_rate": "0.006",
                        "currency": "USD",
                    },
                ],
            )
            self.assertAlmostEqual(run.category_totals["storage"], 0.012025)
            self.assertAlmostEqual(run.category_totals["network"], 0.006)
            text = ibm_cost.format_cli(run)
            self.assertIn("Storage Cost", text)
            self.assertIn("Network Cost", text)
            self.assertIn("$0.0120", text)
            self.assertIn("$0.0060", text)

    def test_multiple_runs_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = self._price(
                tmp,
                name="a",
                run_label="runA",
                lifecycle="create_end_unix=0\nterminate_start_unix=3600\n",
            )
            b = self._price(
                tmp,
                name="b",
                run_label="runB",
                lifecycle="create_end_unix=3600\nterminate_start_unix=7200\n",
            )
            self.assertNotEqual(a.run_id, b.run_id)
            va = [r for r in a.resources if r.usage.resource_type == "vm"][0]
            vb = [r for r in b.resources if r.usage.resource_type == "vm"][0]
            self.assertAlmostEqual(va.total_cost, 10.5)
            self.assertAlmostEqual(vb.total_cost, 10.5)

    def test_shared_resource_time_split(self):
        usage_a = ibm_cost.ResourceUsage(
            resource_id="shared-vm",
            resource_type="vm",
            resource_name="shared",
            sku="bx2-16x64",
            region="us-south",
            quantity=1,
            start_time=0,
            end_time=7200,
            runtime_seconds=7200,
            runtime_source="ibm_lifecycle",
            runtime_is_estimate=False,
            unit="INSTANCE_HOUR",
        )
        usage_b = ibm_cost.ResourceUsage(
            resource_id="shared-vm",
            resource_type="vm",
            resource_name="shared",
            sku="bx2-16x64",
            region="us-south",
            quantity=1,
            start_time=3600,
            end_time=10800,
            runtime_seconds=7200,
            runtime_source="ibm_lifecycle",
            runtime_is_estimate=False,
            unit="INSTANCE_HOUR",
        )
        run_a = ibm_cost.RunCost(
            run_id="A",
            start_time=0,
            end_time=7200,
            runtime_seconds=7200,
            runtime_source="ibm_lifecycle",
            status="completed",
            currency="USD",
            resources=[ibm_cost.calculate_resource_cost(usage_a, 10.0, "t")],
            total_cost=20.0,
            average_cost_per_hour=10.0,
            estimated_24h_cost=240.0,
        )
        run_b = ibm_cost.RunCost(
            run_id="B",
            start_time=3600,
            end_time=10800,
            runtime_seconds=7200,
            runtime_source="ibm_lifecycle",
            status="completed",
            currency="USD",
            resources=[ibm_cost.calculate_resource_cost(usage_b, 10.0, "t")],
            total_cost=20.0,
            average_cost_per_hour=10.0,
            estimated_24h_cost=240.0,
        )
        ibm_cost.apply_shared_attribution([run_a, run_b])
        # overlap 3600s; each own=7200, others=3600 → share 7200/10800 = 2/3
        self.assertAlmostEqual(run_a.resources[0].total_cost, 20.0 * 2 / 3)
        self.assertAlmostEqual(run_b.resources[0].total_cost, 20.0 * 2 / 3)
        self.assertEqual(run_a.resources[0].usage.attribution, "time_overlap")


class EdgeCaseTests(unittest.TestCase):
    def test_resource_started_before_and_stopped_after(self):
        # Lifecycle is still the billable window for this run.
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _run_dir(
                tmp,
                instance_cost="10.5",
                lifecycle="create_end_unix=0\nterminate_start_unix=3600\n",
                test_times="test: linpack execution time 100\n",
            )
            header, usages, _ = ibm_cost.discover_ibm_resources(run_dir)
            self.assertEqual(header["runtime_seconds"], 3600)
            self.assertEqual(header["runtime_source"], "ibm_lifecycle")
            self.assertEqual(usages[0].runtime_seconds, 3600)

    def test_failed_and_partial_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            failed = _run_dir(
                tmp,
                name="fail",
                failed=True,
                lifecycle="create_end_unix=0\nterminate_start_unix=1800\n",
            )
            header, _, _ = ibm_cost.discover_ibm_resources(failed)
            self.assertEqual(header["status"], "failed")
            partial = _run_dir(
                tmp,
                name="part",
                returned=False,
                lifecycle="create_end_unix=0\nterminate_start_unix=1800\n",
            )
            _write(os.path.join(partial, "test_started"), "1\n")
            header, _, _ = ibm_cost.discover_ibm_resources(partial)
            self.assertEqual(header["status"], "partial")

    def test_missing_metadata_falls_back_to_test_times(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _run_dir(
                tmp,
                test_times="test: linpack execution time 120\ntest: streams execution time 60\n",
            )
            header, usages, warnings = ibm_cost.discover_ibm_resources(run_dir)
            self.assertEqual(header["runtime_seconds"], 180)
            self.assertEqual(header["runtime_source"], "zathras_test_times")
            self.assertTrue(usages[0].runtime_is_estimate)
            self.assertTrue(any("test_times" in w for w in warnings))

    def test_configured_runtime_is_labeled_estimate(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _run_dir(tmp, name="cfg")
            header, usages, warnings = ibm_cost.discover_ibm_resources(
                run_dir, configured_runtime_seconds=900
            )
            self.assertEqual(header["runtime_seconds"], 900)
            self.assertEqual(header["runtime_source"], "configured_runtime")
            self.assertTrue(usages[0].runtime_is_estimate)
            self.assertTrue(any("estimate" in w.lower() for w in warnings))

    def test_instance_cost_file_used_before_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _run_dir(
                tmp,
                instance_cost="3.25",
                lifecycle="create_end_unix=0\nterminate_start_unix=3600\n",
            )
            called = []

            def boom(sku, region):
                called.append((sku, region))
                raise RuntimeError("should not be called")

            header, usages, _ = ibm_cost.discover_ibm_resources(run_dir)
            vms = [u for u in usages if u.resource_type == "vm"]
            run = ibm_cost.price_run(
                header, vms, overrides=[], instance_cost=3.25, catalog_lookup=boom
            )
            self.assertEqual(called, [])
            self.assertAlmostEqual(run.resources[0].total_cost, 3.25)
            self.assertEqual(run.resources[0].pricing_source, "run_instance_cost")

    def test_catalog_timeout_unavailable(self):
        def timeout(sku, region):
            raise TimeoutError("API timeout")

        rate, source, _cur = ibm_cost.resolve_rate(
            "vm",
            "bx2-16x64",
            "us-south",
            overrides=[],
            catalog_lookup=timeout,
        )
        self.assertIsNone(rate)
        self.assertIn("catalog_error", source)

    def test_deleted_resource_still_costed_from_local_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _run_dir(
                tmp,
                instance_cost="1.0",
                lifecycle="create_end_unix=1000\nterminate_start_unix=4600\n",
                meta="instance_id: gone-from-ibm\n",
            )
            header, usages, _ = ibm_cost.discover_ibm_resources(run_dir)
            self.assertEqual(header["runtime_seconds"], 3600)
            self.assertTrue(any(u.resource_type == "vm" for u in usages))

    def test_average_cost_per_hour_not_sum_of_rates(self):
        vm = ibm_cost.ResourceUsage(
            resource_id="vm",
            resource_type="vm",
            resource_name="vm",
            sku="bx2-16x64",
            region="us-south",
            quantity=1,
            start_time=0,
            end_time=7200,
            runtime_seconds=7200,
            runtime_source="ibm_lifecycle",
            runtime_is_estimate=False,
            unit="INSTANCE_HOUR",
        )
        gpu = ibm_cost.ResourceUsage(
            resource_id="gpu",
            resource_type="gpu",
            resource_name="gpu",
            sku="gx2",
            region="us-south",
            quantity=1,
            start_time=0,
            end_time=3600,
            runtime_seconds=3600,
            runtime_source="ibm_lifecycle",
            runtime_is_estimate=False,
            unit="GPU_HOUR",
        )
        header = {
            "run_id": "r",
            "start_time": 0,
            "end_time": 7200,
            "runtime_seconds": 7200,
            "runtime_source": "ibm_lifecycle",
            "status": "completed",
        }
        run = ibm_cost.price_run(
            header,
            [vm, gpu],
            overrides=[
                {
                    "resource_type": "vm",
                    "sku": "bx2-16x64",
                    "region": "us-south",
                    "unit": "INSTANCE_HOUR",
                    "hourly_rate": "10",
                    "currency": "USD",
                },
                {
                    "resource_type": "gpu",
                    "sku": "gx2",
                    "region": "us-south",
                    "unit": "GPU_HOUR",
                    "hourly_rate": "20",
                    "currency": "USD",
                },
            ],
        )
        # total = 10*2 + 20*1 = 40; run hours = 2; avg = 20 != 10+20
        self.assertAlmostEqual(run.total_cost, 40.0)
        self.assertAlmostEqual(run.average_cost_per_hour, 20.0)
        self.assertNotAlmostEqual(run.average_cost_per_hour, 30.0)

    def test_sqlite_and_json_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _run_dir(
                tmp,
                instance_cost="10.5",
                lifecycle="create_end_unix=0\nterminate_start_unix=3600\n",
            )
            run = ibm_cost.cost_run_dir(
                run_dir,
                overrides_path=os.path.join(tmp, "none.cfg"),
                volume_lookup=None,
                floating_ip_lookup=None,
            )
            db = os.path.join(tmp, "zathras_cost.db")
            ibm_cost.persist(run, db)
            conn = sqlite3.connect(db)
            cur = conn.execute("select run_id, total_cost from zathras_run")
            row = cur.fetchone()
            self.assertEqual(row[0], run.run_id)
            payload = ibm_cost.run_to_json(run)
            self.assertEqual(payload["run_id"], run.run_id)
            self.assertIn("resources", payload)
            text = ibm_cost.format_cli(run)
            self.assertIn("TOTAL COST", text)
            self.assertIn("Estimated 24-hour cost", text)

    def test_cli_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _run_dir(
                tmp,
                instance_cost="10.5",
                lifecycle="create_end_unix=0\nterminate_start_unix=15120\n",
            )
            # Offline: inject storage/network rates instead of live catalog.
            run = ibm_cost.cost_run_dir(
                run_dir,
                volume_lookup=lambda _p, _r: 0.00012025,
                floating_ip_lookup=lambda _r: 0.006,
            )
            payload = ibm_cost.run_to_json(run)
            self.assertAlmostEqual(payload["runtime_hours"], 4.2)
            self.assertAlmostEqual(payload["category_totals"]["vm"], 44.1)
            # 100 GB × 4.2 h × 0.00012025
            self.assertAlmostEqual(
                payload["category_totals"]["storage"], 100 * 4.2 * 0.00012025, places=6
            )
            self.assertAlmostEqual(
                payload["category_totals"]["network"], 4.2 * 0.006, places=6
            )
            self.assertEqual(payload["category_totals"]["gpu"], 0.0)

class TerraformInventoryTests(unittest.TestCase):
    def test_classifies_billable_and_not_billable(self):
        doc = {
            "values": {
                "root_module": {
                    "resources": [
                        {
                            "address": "ibm_is_instance.test[0]",
                            "type": "ibm_is_instance",
                            "values": {
                                "id": "vm-1",
                                "name": "zathras-bx2",
                                "profile": "bx2-4x16",
                                "boot_volume": [{"size": 100}],
                            },
                        },
                        {
                            "address": "ibm_is_vpc.zathras_vpc[0]",
                            "type": "ibm_is_vpc",
                            "values": {"id": "vpc-1", "name": "zathras-vpc"},
                        },
                        {
                            "address": "ibm_is_subnet.zathras_subnet",
                            "type": "ibm_is_subnet",
                            "values": {"id": "sub-1", "name": "zathras-subnet"},
                        },
                        {
                            "address": "ibm_is_floating_ip.zathras_floating_ip[0]",
                            "type": "ibm_is_floating_ip",
                            "values": {"id": "fip-1", "name": "zathras-fip"},
                        },
                    ]
                }
            }
        }
        usages = ibm_cost.resources_from_terraform_inventory(
            doc, region="us-south", start=0, end=3600, seconds=3600,
            source="terraform_apply_to_destroy", estimate=False,
        )
        types = {u.resource_type for u in usages}
        self.assertIn("vm", types)
        self.assertIn("floating_ip", types)
        self.assertIn("volume", types)
        self.assertIn("not_billed", types)
        billed = [u for u in usages if u.billable]
        not_billed = [u for u in usages if not u.billable]
        self.assertTrue(any(u.sku == "bx2-4x16" for u in billed))
        self.assertTrue(any("VPC" in u.notes for u in not_billed))

    def test_terraform_timestamps_preferred(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _run_dir(
                tmp,
                lifecycle=(
                    "terraform_apply_end_unix=10\n"
                    "terraform_destroy_end_unix=3610\n"
                    "create_end_unix=0\n"
                    "terminate_start_unix=100\n"
                ),
            )
            start, end, seconds, source, estimate, _ = ibm_cost.discover_window(run_dir)
            self.assertEqual(start, 10)
            self.assertEqual(end, 3610)
            self.assertEqual(seconds, 3600)
            self.assertEqual(source, "terraform_apply_to_destroy")
            self.assertFalse(estimate)

    def test_fail_open_does_not_return_error(self):
        rc = ibm_cost.main(["--fail-open", "/no/such/run/dir"])
        self.assertEqual(rc, 0)

    def test_representative_bx2_run_categories(self):
        """Mirror gist run: bx2-4x16, boot volume, floating IP, no GPU/data disks."""
        with tempfile.TemporaryDirectory() as tmp:
            inv = {
                "values": {
                    "root_module": {
                        "resources": [
                            {
                                "address": "ibm_is_instance.test[0]",
                                "type": "ibm_is_instance",
                                "values": {
                                    "id": "0727_ae7fb19b",
                                    "name": "sbhavsar-ibmcla-bx2-4x16-0",
                                    "profile": "bx2-4x16",
                                    "boot_volume": [{"size": 100}],
                                },
                            },
                            {
                                "address": "ibm_is_floating_ip.zathras_floating_ip[0]",
                                "type": "ibm_is_floating_ip",
                                "values": {"id": "r006-d0f613bc", "name": "fip-0"},
                            },
                            {
                                "address": "ibm_is_vpc.zathras_vpc[0]",
                                "type": "ibm_is_vpc",
                                "values": {"id": "vpc-1", "name": "zathras-vpc"},
                            },
                            {
                                "address": "ibm_is_subnet.zathras_subnet",
                                "type": "ibm_is_subnet",
                                "values": {"id": "sub-1", "name": "zathras-subnet"},
                            },
                            {
                                "address": "ibm_is_security_group.zathras_sg",
                                "type": "ibm_is_security_group",
                                "values": {"id": "sg-1", "name": "zathras-sg"},
                            },
                        ]
                    }
                }
            }
            run_dir = _run_dir(
                tmp,
                sku="bx2-4x16",
                instance_cost="0.201",
                lifecycle=(
                    "terraform_apply_end_unix=0\n"
                    "terraform_destroy_end_unix=3600\n"
                ),
            )
            with open(
                os.path.join(run_dir, "terraform_inventory.json"),
                "w",
                encoding="utf-8",
            ) as fh:
                json.dump(inv, fh)
            header, usages, warnings = ibm_cost.discover_ibm_resources(run_dir)
            run = ibm_cost.price_run(
                header,
                usages,
                overrides=[],
                instance_cost=0.201,
                volume_lookup=lambda _p, _r: 0.00012025,
                floating_ip_lookup=lambda _r: 0.006,
                warnings=warnings,
            )
            self.assertAlmostEqual(run.category_totals["vm"], 0.201)
            self.assertAlmostEqual(run.category_totals["gpu"], 0.0)
            self.assertAlmostEqual(run.category_totals["storage"], 0.012025)
            self.assertAlmostEqual(run.category_totals["network"], 0.006)
            self.assertAlmostEqual(run.total_cost, 0.201 + 0.012025 + 0.006)
            self.assertTrue(any(not u.billable for u in usages))


def run_self_test() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(run_self_test())
