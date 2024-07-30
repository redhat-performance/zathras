## Table of Contents
- [About](#about)
- [How It Works](#how-it-works)
- [Installation and Quick Start](#installation-and-quick-start)
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
2. Zathras runs using either a configuration file or by supplying parameters in your command-line interface (CLI).  
3. Test(s) run on the system under test (SUT).
4. When tests finish, Zathras copies the results back to the controller system.
5. Once results have been retrieved, Zathras will attempt to cleanup the testing environment (such as by tearing down instances in the cloud or by removing directories and files on bare metal). 

The user configures the Zathras installation with information about the system under test (SUT) and what test(s) to run.

## Getting Started

### Requirements
- git 

### Installation
First, clone this repository to your controller system.

### Testing Quickstarts
In general, testing with Zathras follows a similar set of steps across modalities: configure the tests to run, then run burden via the command line. 



However, there are some aspects that are particular to the testing environment being used.

- Testing on bare metal
- Testing on cloud
- Testing on virtualization

## License