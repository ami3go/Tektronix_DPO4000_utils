# Robot Framework Tests for DPO4000 Job

This directory contains Robot Framework tests that demonstrate how to execute the `dpo4000-job` CLI tool.

## Running Tests

To run these tests, first install Robot Framework:
```
pip install robotframework
```

Run the tests (excluding hardware tests):
```
robot --exclude hardware examples/robot_framework/
```

To run the hardware test, set the `DPO4000_RESOURCE` environment variable:
```
DPO4000_RESOURCE='USB0::0x0699::0x0401::C000000::INSTR' robot examples/robot_framework/
```

## Test Cases

1. **Recipe Validates Without Instrument I/O**: Validates the recipe and rules without using hardware
2. **Scope Meets Acceptance Rules**: Executes the full test with hardware (requires `DPO4000_RESOURCE`)

## Exit Codes

- 0: Success
- 2: Validation error
- 3: Runtime error
- 4: Recipe failed
- 5: Rule failed (DUT failed acceptance criteria)
- 6: Rule invalid (a rule input was missing or non-numeric; malformed rules files are exit 2)
- 7: Export error
- 130: Cancelled

> **Note**: the offline test case was run locally with Robot Framework 7; the hardware case and CI execution are not yet qualified.
