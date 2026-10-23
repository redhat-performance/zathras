# Azure create role

Provisions Azure Linux VMs via Terraform for Zathras.

## Cost tracking

Isolated plugin (same flag as IBM). Failures never fail the run.

```bash
./bin/burden --scenario <azure-scenario.yml> --track_cost 1
# after the run:
./bin/burden cost --latest
```

Prices come from the public Azure Retail Prices API (USD), optional
`config/azure_pricing_overrides.cfg`, and the run's `instance_cost` file.
Missing rates are reported as unavailable — never invented.

Reports: `cost_report.txt` (TL;DR + detail), `cost_report.json`, `zathras_cost.db`.
