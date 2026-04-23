# CI Test Scenarios

This directory contains test scenario files used by GitHub Actions workflows to validate Zathras across different cloud providers and bare metal systems.

## Scenario Files

- **aws_ci_test.yml** - AWS cloud testing scenario
- **azure_ci_test.yml** - Azure cloud testing scenario
- **gcp_ci_test.yml** - GCP cloud testing scenario
- **baremetal_ci_test.yml** - Bare metal/local system testing scenario

## Test Coverage

Each scenario runs a standard test suite consisting of:
- **linpack** - CPU performance benchmark (5 min)
- **streams** - Memory bandwidth benchmark (3 min)
- **fio** - I/O performance benchmark (4 min total for read/write/randread/randwrite)

Total estimated runtime per cloud: **~15-20 minutes** (including provisioning and cleanup)

## Configuration

Cloud scenarios are configured to:
- Use medium-sized instances (cost-effective for testing)
- Enable spot/preemptible instances where possible (cost optimization)
- Use minimal disk sizes (100GB)
- Automatically terminate cloud resources after testing
- Run shortened benchmark durations (faster feedback)

## Customization

To modify test parameters:
1. Edit the relevant scenario file
2. Adjust `linpack_run_time`, `streams_run_time`, or `fio_runtime` values
3. Add/remove tests from the `tests:` list
4. Modify instance types in `host_config:` if needed

## Usage in CI

GitHub Actions workflows use these scenarios with runtime parameter substitution:
- Cloud OS IDs are set via environment variables
- SSH keys are configured from GitHub secrets
- Region/zone can be overridden for geographic testing

See `.github/workflows/test-*.yml` for implementation details.
