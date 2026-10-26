# OpenTAP DPO4000 Job Step

This directory contains an example OpenTAP Python plugin that wraps the `dpo4000-job` CLI tool.

## Installation

To use this test step in OpenTAP:

1. Copy `dpo4000_job_step.py` into your OpenTAP Python plugin package
2. Ensure `dpo4000-utils` is installed in your environment: `pip install dpo4000-utils`
3. This will make the `dpo4000-job` CLI available on the PATH

## Functionality

This test step executes a dpo4000-job recipe with specified parameters:
- Recipe file path
- Rules file path (optional)
- Resource path (for hardware tests)
- Report output path
- Timeout value

## Verdict Mapping

| Exit Code | OpenTAP Verdict |
|-----------|-----------------|
| 0         | Pass            |
| 5, 6      | Fail            |
| 130       | Aborted         |
| Other     | Error           |

> **Note**: This is an untested example. The OpenTAP environment is not available in this repo's CI.
