## Table of Contents
- [About](#about)
- [How It Works](#how-it-works)
- [Getting started](#getting-started)
    - [Requirements](#requirements)
    - [Installation](#installation)
    - [Test config files](#test-config-files)
    - [Testing Quick Start](#installation-and-quick-start)
- [License](#license)

## About
Zathras is a test automation framework for use with bare metal, cloud, and virtualized systems. Tests are defined by wrappers - external, self-contained scripts that enable easy extension of Zathras's functionality. 

Currently, Zathras offers the following test wrappers:

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
- yq, version 2.10.0 (newer versions currently break Zathras)
- wget

### Installation
Installing Zathras is easy! First, clone this repository to your controller system.

    git clone https://github.com/redhat-performance/zathras.git

Installation can then be completed by running the install script located within the repo's bin/ directory:

    ./install.sh


Note: for most installations the install script should be run as a user, not root.

### Test config files
Test config files, stored in the config/ directory of the Zathras installation, are the connective tissue between Zathras and the test wrappers. Currently this Zathras repo does not contain any defined test config files. Before you can use this tool, you will need to write your own test configs using the included example.yml, or add the configs from an external source if one is available to you.

### Testing Quickstarts
In general, testing with Zathras follows a similar set of steps across modalities: configure the tests to run, then run burden via the command line. 


However, there are some aspects that are particular to the testing environment being used. Please refer to the following documentation that matches your use case:

- Testing on bare metal
- Testing on cloud
- Testing on virtualization

## License
