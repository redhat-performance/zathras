## Table of Contents
- [About](#about)
- [How It Works](#how-it-works)
- [Getting started](#getting-started)
    - [Requirements](#requirements)
    - [Installation](#installation)
    - [Test config files](#test-config-files)
    - [Testing Quick Starts](#installation-and-quick-start)


## About
Zathras is a test automation framework for use with bare metal, cloud, and virtualized systems. Tests are defined by wrappers - external, self-contained scripts that enable easy extension of Zathras's functionality. 

Currently (as of September 2025), Zathras offers the following test wrappers:

| Test Name                                          | Description                                                                         | Wrapper URL                                                |
|----------------------------------------------------|-------------------------------------------------------------------------------------|------------------------------------------------------------|
| CoreMark                                           | Test processor core functionality                                                   | https://github.com/redhat-performance/coremark-wrapper     |
| CoreMark Pro                                       | EEMBC's advanced processor benchmark.                                               | https://github.com/redhat-performance/coremark_pro-wrapper |
| Flexible I/O tester                                | Test the Linux I/O subsystem and schedulers                                         | https://github.com/redhat-performance/fio-wrapper          |
| HPL                                                | Freely available implementation of the High Performance Computing Linpack Benchmark | https://github.com/redhat-performance/autohpl-wrapper      |
| HammerDB                                           | Database benchmarking                                                               | https://github.com/redhat-performance/hammerdb-wrapper     |
| IOzone                                             | File system benchmarking                                                            | https://github.com/redhat-performance/iozone-wrapper       |
| Linpack                                            | Licensed version of Linpack benchmark (see also: HPL)                               | https://github.com/redhat-performance/linpack-wrapper      |
| NUMA STREAM                                        | Extension of STREAM benchmark to measure NUMA effects                               | https://github.com/redhat-performance/numa_streams-wrapper |
| Passmark                                           | CPU benchmark                                                                       | https://github.com/redhat-performance/passmark-wrapper     |
| Phoronix Test Suite                                | Comprehensive automated testing and benchmarking platform                           | https://github.com/redhat-performance/phoronix-wrapper     |
| pig                                                | Processor scheduler efficiency test                                                 | https://github.com/redhat-performance/pig_wrapper          |
| Python Performance Benchmark Suite (pyperformance) | Performance testing for Python using real-world benchmarks                          | https://github.com/redhat-performance/pyperf-wrapper       |
| SPEC CPU 2017                                      | Suite of benchmarks for compute-intensive performance                               | https://github.com/redhat-performance/speccpu2017-wrapper  |
| SPEC JBB2005                                       | Evaluate the performance of server side Java                                        | https://github.com/redhat-performance/specjbb-wrapper      |
| STREAM                                             | Benchmark for sustained memory bandwidth                                            | https://github.com/redhat-performance/streams-wrapper      |
| Uperf                                              | Network performance testing                                                         | https://github.com/redhat-performance/uperf-wrapper        |

## How It Works
1. Zathras is installed to a controller system.
2. Zathras runs using either a configuration file or by supplying parameters in your command-line interface (CLI) (see the [CLI reference](docs/command_line_reference.md) for more info).  
3. Test(s) run on the system under test (SUT).
4. When tests finish, Zathras copies the results back to the controller system.
5. Once results have been retrieved, Zathras will attempt to cleanup the testing environment (such as by tearing down instances in the cloud or by removing directories and files on bare metal). 

The user configures the Zathras installation with information about the system under test (SUT) and what test(s) to run.

## Getting Started

### Requirements
To use Zathras, you need: 
1. A system that will coordinate the execution of tests, which we will call the *control node* or simply the *controller*.
2. One or more systems where tests will be run. This can be another physical system (aka bare metal), an instance on a public cloud like Amazon Web Services (AWS), or even a virtual machine (VM) either on the controller or another host system.

The following packages will need to be installed on the controller to run Zathras. If you use the included installer script (next section), they will be installed for you.
- ansible-core
- git
- jq
- python
- python3-pip
- terraform
- unzip
- wget
- yq, version 2.10.0 (newer versions currently break Zathras)

Additional Python packages installed automatically:
- boto
- boto3

Additional Ansible collections installed automatically:
- amazon.aws
- ansible.posix

### Installation
Installing Zathras is easy! First, clone this repository to your controller system.

    git clone https://github.com/redhat-performance/zathras.git

Installation can then be completed by running the install script located within the repo's bin/ directory:

    ./install.sh


Note: for most installations the install script should be run as a user, not root.

### Test config files
Test config files, stored in the config/ directory of the Zathras installation, are the connective tissue between Zathras and the test wrappers. Zathras comes with pre-configured test definitions for all supported test wrappers, including:

- **test_defs.yml** - Main test definitions file with 18+ pre-configured tests
- **Template files** - Individual configuration templates for each test wrapper (e.g., linpack_template.yml, streams_template.yml)
- **java_pkg_def.yml** - Java package definitions for different OS vendors
- **default_template.yml** - Default settings applied to all tests

You can use these configurations as-is or customize them for your specific requirements. The process of understanding and modifying test configuration files is explained [here](docs/test_config_files.md).

### Testing Quickstarts
In general, testing with Zathras follows a similar set of steps across modalities: configure the tests to run, then run burden via the command line. 

However, there are some aspects that are particular to the testing environment being used. Please refer to the following documentation that matches your use case:

- [Testing on bare metal](docs/testing_quickstart.md#testing-on-bare-metal)
- [Testing on cloud](docs/testing_quickstart.md#testing-on-cloud)
- [Testing on virtualization](docs/testing_quickstart.md#testing-in-virtualization)

## Additional Documentation

For more detailed information, see:

- **[Command Line Reference](docs/command_line_reference.md)** - Complete CLI options and usage
- **[Test Configuration Files](docs/test_config_files.md)** - How to configure tests
- **[Scenario Files](docs/scenario_files.md)** - Advanced scenario configuration
- **[Testing Quickstart](docs/testing_quickstart.md)** - Step-by-step testing guides
- **[Bare Metal Configuration](docs/bare_metal_configuration.md)** - Local system configuration for bare metal testing
