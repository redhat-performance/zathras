#!/usr/bin/env python3
"""Unit tests for Azure Zathras cost tracking. No live Azure API calls."""

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

import azure_cost  # noqa: E402
import azure_instance_price as azprice  # noqa: E402


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def _run_dir(tmp: str, **kwargs) -> str:
    path = os.path.join(tmp, kwargs.get("name", "0_Standard_D2s_v3"))
    os.makedirs(path, exist_ok=True)
    sku = kwargs.get("sku", "Standard_D2s_v3")
    region = kwargs.get("region", "eastus")
    disks = kwargs.get("disks", "none")
    networks = kwargs.get("networks", "0")
    run_label = kwargs.get("run_label", "alice_rhel")
    vm_type = kwargs.get("vm_type", "regular")
    spot_start = kwargs.get("spot_start_price", "0")
    _write(
        os.path.join(path, "ansible_vars_main.yml"),
        (
            "---\n"
            "config_info:\n"
            f"  system_type: azure\n"
            f"  host_or_cloud_inst: {sku}\n"
            f"  host_config: {sku}\n"
            f"  cloud_region: {region}\n"
            f"  run_label: {run_label}\n"
            f"  cloud_disks: {disks}\n"
            f"  cloud_numb_networks: {networks}\n"
            f"  vm_type: {vm_type}\n"
            f"  spot_start_price: {spot_start}\n"
        ),
    )
    if "instance_cost" in kwargs:
        _write(os.path.join(path, "instance_cost"), str(kwargs["instance_cost"]) + "\n")
    if "lifecycle" in kwargs:
        _write(os.path.join(path, "instance_lifecycle"), kwargs["lifecycle"])
    if "test_times" in kwargs:
        _write(os.path.join(path, "test_times"), kwargs["test_times"])
    if kwargs.get("failed"):
        _write(os.path.join(path, "cpu_type_failure"), "1\n")
    if kwargs.get("returned", True):
        _write(os.path.join(path, "test_returned"), "Test completed\n")
    if "tf_inventory" in kwargs:
        _write(
            os.path.join(path, "terraform_inventory.json"),
            json.dumps(kwargs["tf_inventory"]),
        )
    return path


def _tf_doc(
    *,
    sku="Standard_D2s_v3",
    region="eastus",
    os_disk_gb=30,
    data_disk_gb=None,
    data_disk_type="Premium_LRS",
):
    resources = [
        {
            "address": "azurerm_resource_group.resource_group",
            "type": "azurerm_resource_group",
            "values": {"id": "/rg/1", "name": "rg1", "location": region},
        },
        {
            "address": "azurerm_linux_virtual_machine.virtualmachine[0]",
            "type": "azurerm_linux_virtual_machine",
            "values": {
                "id": "/vm/1",
                "name": "alice-vm",
                "location": region,
                "size": sku,
                "os_disk": {
                    "storage_account_type": "Premium_LRS",
                    "disk_size_gb": os_disk_gb,
                },
            },
        },
        {
            "address": "azurerm_public_ip.publicip[0]",
            "type": "azurerm_public_ip",
            "values": {
                "id": "/pip/1",
                "name": "alice-publicip-00",
                "location": region,
                "sku": "Basic",
                "allocation_method": "Dynamic",
            },
        },
        {
            "address": "azurerm_virtual_network.vnet",
            "type": "azurerm_virtual_network",
            "values": {"id": "/vnet/1", "name": "vnet", "location": region},
        },
    ]
    if data_disk_gb is not None:
        resources.append(
            {
                "address": "azurerm_managed_disk.datadisk[0]",
                "type": "azurerm_managed_disk",
                "values": {
                    "id": "/disk/1",
                    "name": "alice-disk0",
                    "location": region,
                    "storage_account_type": data_disk_type,
                    "disk_size_gb": data_disk_gb,
                },
            }
        )
    return {"values": {"root_module": {"resources": resources}}}


class RuntimeTests(unittest.TestCase):
    def test_hours(self):
        self.assertAlmostEqual(azure_cost.hours_from_seconds(3600), 1.0)
        self.assertEqual(azure_cost.runtime_seconds(0, 3600)[0], 3600)


class PriceHelperTests(unittest.TestCase):
    def test_premium_ssd_tier(self):
        self.assertEqual(azprice.premium_ssd_tier(30), "P4")
        self.assertEqual(azprice.premium_ssd_tier(128), "P10")
        self.assertEqual(azprice.premium_ssd_tier(1000), "P30")

    def test_monthly_to_hourly(self):
        self.assertAlmostEqual(azprice.monthly_to_hourly(73.0), 73.0 / azprice.HOURS_PER_MONTH)

    def test_pick_vm_ondemand_linux(self):
        items = [
            {
                "type": "Consumption",
                "productName": "Virtual Machines Dsv3 Series Windows",
                "meterName": "D2s v3",
                "skuName": "D2s v3",
                "unitOfMeasure": "1 Hour",
                "retailPrice": 0.2,
                "isPrimaryMeterRegion": True,
            },
            {
                "type": "Consumption",
                "productName": "Virtual Machines Dsv3 Series",
                "meterName": "D2s v3",
                "skuName": "D2s v3",
                "unitOfMeasure": "1 Hour",
                "retailPrice": 0.096,
                "isPrimaryMeterRegion": True,
            },
            {
                "type": "Consumption",
                "productName": "Virtual Machines Dsv3 Series",
                "meterName": "D2s v3 Spot",
                "skuName": "D2s v3 Spot",
                "unitOfMeasure": "1 Hour",
                "retailPrice": 0.02,
                "isPrimaryMeterRegion": True,
            },
        ]
        chosen = azprice._pick_vm_item(items, spot=False)
        self.assertAlmostEqual(chosen["retailPrice"], 0.096)
        spot = azprice._pick_vm_item(items, spot=True)
        self.assertAlmostEqual(spot["retailPrice"], 0.02)

    def test_lookup_vm_with_fixture_fetch(self):
        payload = {
            "Items": [
                {
                    "type": "Consumption",
                    "productName": "Virtual Machines Dsv3 Series",
                    "meterName": "D2s v3",
                    "skuName": "D2s v3",
                    "unitOfMeasure": "1 Hour",
                    "retailPrice": 0.096,
                    "armSkuName": "Standard_D2s_v3",
                    "armRegionName": "eastus",
                    "isPrimaryMeterRegion": True,
                }
            ],
            "NextPageLink": None,
        }

        def fetch(url, timeout):
            return payload

        price = azprice.lookup_vm_hourly_price(
            "Standard_D2s_v3", "eastus", fetch=fetch
        )
        self.assertAlmostEqual(price, 0.096)

    def test_missing_meter_raises(self):
        def fetch(url, timeout):
            return {"Items": [], "NextPageLink": None}

        with self.assertRaises(azprice.AzurePriceError):
            azprice.lookup_vm_hourly_price("Standard_NoSuch", "eastus", fetch=fetch)


class CostScenarioTests(unittest.TestCase):
    def _price(self, tmp, **kwargs):
        run_dir = _run_dir(tmp, **kwargs)
        return azure_cost.cost_run_dir(
            run_dir,
            vm_lookup=kwargs.get("vm_lookup", lambda s, r, spot=False: 0.096),
            disk_lookup=kwargs.get(
                "disk_lookup", lambda t, r, gb: azprice.monthly_to_hourly(5.0)
            ),
            pip_lookup=kwargs.get("pip_lookup", lambda r, sku="Basic": 0.004),
        )

    def test_one_vm_one_hour(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._price(
                tmp,
                instance_cost="0.096",
                lifecycle="create_end_unix=0\nterminate_start_unix=3600\n",
                tf_inventory=_tf_doc(os_disk_gb=30),
            )
            self.assertAlmostEqual(run.category_totals["vm"], 0.096)
            self.assertGreater(run.category_totals["storage"], 0.0)
            self.assertAlmostEqual(run.category_totals["network"], 0.004)
            self.assertAlmostEqual(run.category_totals["gpu"], 0.0)
            text = azure_cost.format_cli(run)
            self.assertIn("TL;DR", text)
            self.assertIn("pip", text)
            self.assertIn("TOTAL", text)

    def test_override_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            ov = os.path.join(tmp, "ov.cfg")
            _write(
                ov,
                "vm Standard_D2s_v3 eastus INSTANCE_HOUR 1.5 USD\n",
            )
            run_dir = _run_dir(
                tmp,
                instance_cost="0.096",
                lifecycle="create_end_unix=0\nterminate_start_unix=3600\n",
                tf_inventory=_tf_doc(),
            )
            run = azure_cost.cost_run_dir(
                run_dir,
                overrides_path=ov,
                vm_lookup=lambda s, r, spot=False: 0.096,
                disk_lookup=lambda t, r, gb: 0.001,
                pip_lookup=lambda r, sku="Basic": 0.004,
            )
            vm = [r for r in run.resources if r.usage.resource_type == "vm"][0]
            self.assertAlmostEqual(vm.total_cost, 1.5)
            self.assertEqual(vm.pricing_source, "pricing_override")

    def test_missing_os_disk_size_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = _tf_doc()
            # Remove disk_size_gb
            for r in doc["values"]["root_module"]["resources"]:
                if r["type"] == "azurerm_linux_virtual_machine":
                    r["values"]["os_disk"] = {"storage_account_type": "Premium_LRS"}
            run = self._price(
                tmp,
                instance_cost="0.096",
                lifecycle="create_end_unix=0\nterminate_start_unix=3600\n",
                tf_inventory=doc,
            )
            osdisk = [
                r
                for r in run.resources
                if r.usage.resource_type == "volume" and "osdisk" in r.usage.resource_name
            ][0]
            self.assertIsNone(osdisk.total_cost)
            self.assertTrue(any("OS disk size" in w for w in run.warnings))

    def test_spot_flag_passed_to_lookup(self):
        seen = {}

        def vm_lookup(sku, region, spot=False):
            seen["spot"] = spot
            return 0.02

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _run_dir(
                tmp,
                vm_type="preemptible",
                spot_start_price="1",
                lifecycle="create_end_unix=0\nterminate_start_unix=3600\n",
                tf_inventory=_tf_doc(),
            )
            azure_cost.cost_run_dir(
                run_dir,
                vm_lookup=vm_lookup,
                disk_lookup=lambda t, r, gb: 0.001,
                pip_lookup=lambda r, sku="Basic": 0.004,
            )
            self.assertTrue(seen.get("spot"))

    def test_gpu_note_no_separate_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._price(
                tmp,
                sku="Standard_NC6s_v3",
                instance_cost="1.0",
                lifecycle="create_end_unix=0\nterminate_start_unix=3600\n",
                tf_inventory=_tf_doc(sku="Standard_NC6s_v3"),
            )
            gpus = [r for r in run.resources if r.usage.resource_type == "gpu"]
            self.assertEqual(gpus, [])
            self.assertAlmostEqual(run.category_totals["gpu"], 0.0)
            self.assertTrue(any("GPU-capable" in w for w in run.warnings))

    def test_not_billed_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._price(
                tmp,
                instance_cost="0.096",
                lifecycle="create_end_unix=0\nterminate_start_unix=3600\n",
                tf_inventory=_tf_doc(),
            )
            types = {r.usage.resource_type for r in run.resources}
            self.assertIn("not_billed", types)
            text = azure_cost.format_cli(run)
            self.assertIn("Not billed", text)

    def test_fail_open(self):
        rc = azure_cost.main(["--fail-open", "/no/such/run/dir"])
        self.assertEqual(rc, 0)

    def test_sqlite_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _run_dir(
                tmp,
                instance_cost="0.096",
                lifecycle="create_end_unix=0\nterminate_start_unix=7200\n",
                tf_inventory=_tf_doc(os_disk_gb=30, data_disk_gb=128),
            )
            run = azure_cost.cost_run_dir(
                run_dir,
                vm_lookup=lambda s, r, spot=False: 0.096,
                disk_lookup=lambda t, r, gb: 0.001,
                pip_lookup=lambda r, sku="Basic": 0.004,
            )
            db = os.path.join(tmp, "zathras_cost.db")
            azure_cost.persist(run, db)
            conn = sqlite3.connect(db)
            row = conn.execute("select cloud, total_cost from zathras_run").fetchone()
            self.assertEqual(row[0], "azure")
            payload = azure_cost.run_to_json(run)
            self.assertEqual(payload["cloud"], "azure")
            self.assertIn("resources", payload)
            text = azure_cost.format_cli(run)
            self.assertIn("Estimated 24-hour cost", text)


class AnsibleFallbackTests(unittest.TestCase):
    def test_infers_without_terraform(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _run_dir(
                tmp,
                instance_cost="0.1",
                lifecycle="create_end_unix=0\nterminate_start_unix=3600\n",
                disks="1:Premium_LRS:128",
            )
            run = azure_cost.cost_run_dir(
                run_dir,
                vm_lookup=lambda s, r, spot=False: 0.1,
                disk_lookup=lambda t, r, gb: 0.002,
                pip_lookup=lambda r, sku="Basic": 0.004,
            )
            self.assertTrue(any("terraform_inventory" in w for w in run.warnings))
            types = [r.usage.resource_type for r in run.resources if r.usage.billable]
            self.assertIn("vm", types)
            self.assertIn("public_ip", types)
            # data disk from cloud_disks should be present and priced
            data = [
                r
                for r in run.resources
                if r.usage.resource_type == "volume" and r.usage.disk_size_gb == 128
            ]
            self.assertEqual(len(data), 1)
            self.assertAlmostEqual(data[0].total_cost, 0.002)


if __name__ == "__main__":
    unittest.main()
