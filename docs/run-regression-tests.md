# Running the Regression Test Suite

This guide covers the software regression suite and the real-hardware DPO4054 + Probe Comp regression baseline workflow.

## 1. Prepare the repository

From PowerShell:

```powershell
git fetch
git switch test/r0-regression-baseline
git pull
python -m pip install -e .[dev]
```

For normal use after PR #29 is merged, switch to `main` instead.

## 2. Run the software regression suite

Run the complete pytest suite:

```powershell
pytest -q
```

Run only the new regression tests:

```powershell
pytest -q tests/test_regression_*.py
```

Run Ruff as well:

```powershell
ruff check dpo4000_utils tests scripts tektronix_utils.py
```

These tests do not require a physical oscilloscope. They cover the R0 functional snapshot, malformed/boundary input handling, deterministic timing semantics, performance-gate calculations, backpressure, fake-I/O latency/failure behavior, and GUI responsiveness.

## 3. Real-hardware setup

Use the DPO4054 front-panel Probe Comp output as the test signal:

```text
DPO4054 PROBE COMP
        |
        +----> CH1 probe input

Probe Comp GND
        |
        +----> probe ground
```

Use CH1 in normal high-impedance/probe mode. Do not use 50-ohm termination.

The Probe Comp signal is expected to be approximately 1 kHz and about 2.5 Vpp. The runner verifies the signal before executing the hardware cases.

## 4. Optional single hardware HIL run

Before creating a performance baseline, the complete hardware functional suite can be run once:

```powershell
python scripts/run_automation_logger_hil.py `
  --resource "TCPIP0::192.168.0.5::INSTR" `
  --channel 1 `
  --suite all `
  --waveform-points 1000 `
  --output-dir "hardware_verification_reports\automation_logger_hil"
```

Expected qualified result with Probe Comp is currently:

```text
PASS: 23
FAIL: 0
SKIP: 1
```

The expected SKIP is decoded BUS logging because Probe Comp cannot provide a serial-bus stimulus.

Each run restores the original scope setup and writes a diagnostic ZIP containing the HIL report, chronological log, artifacts, environment information, tracebacks, and before/after scope setup snapshots.

## 5. Create the R0 hardware performance baseline

Use the same DPO4054, same PC, same connection type, and the same Probe Comp -> CH1 fixture that will be used for future comparisons.

The default is five complete HIL repetitions:

```powershell
python scripts/run_regression_hardware.py `
  --create-baseline `
  --resource "TCPIP0::192.168.0.5::INSTR" `
  --channel 1 `
  --suite all `
  --waveform-points 1000 `
  --output-dir "hardware_verification_reports\r0_probe_comp"
```

The baseline is written by default to:

```text
hardware_verification_reports\r0_probe_comp\r0_hardware_baseline.json
```

The baseline contains, for every HIL case and for the complete run:

```text
minimum
p50
p95
p99
maximum
sample count
raw timing samples
trend/slope
expected PASS/SKIP status
scope IDN
resource-interface family
fixture configuration
package/platform metadata
```

You can request a different number of repetitions, for example 10:

```powershell
python scripts/run_regression_hardware.py `
  --create-baseline `
  --resource "TCPIP0::192.168.0.5::INSTR" `
  --channel 1 `
  --suite all `
  --repetitions 10 `
  --output-dir "hardware_verification_reports\r0_probe_comp"
```

`--create-baseline` establishes a new reference. Treat the generated JSON as a reviewed qualification artifact; do not recreate it merely to make a later regression pass.

## 6. Compare a candidate against the baseline

After making code changes, run:

```powershell
python scripts/run_regression_hardware.py `
  --compare-baseline `
  --resource "TCPIP0::192.168.0.5::INSTR" `
  --channel 1 `
  --suite all `
  --waveform-points 1000 `
  --output-dir "hardware_verification_reports\r0_probe_comp"
```

Unless `--repetitions` is supplied, comparison uses the repetition count stored in the baseline.

The comparison validates both functional behavior and performance:

- the same scope IDN is used;
- the same connection family is used (`TCPIP` must not be compared directly with `USB`);
- the fixture/configuration matches the baseline;
- the expected PASS/SKIP case set is unchanged;
- no HIL case fails;
- per-case p95 timing stays within the regression gate;
- whole-run p95 timing stays within the regression gate.

The default performance rule is:

```text
FAIL only when
    candidate_p95 > baseline_p95 * 1.30
AND
    candidate_p95 - baseline_p95 > absolute_tolerance
```

Default absolute tolerances are:

```text
per case: 0.25 s
whole run: 2.0 s
```

This dual gate avoids failing on small timing noise while still detecting meaningful slowdowns.

## 7. Custom baseline path and thresholds

A baseline can be stored explicitly:

```powershell
python scripts/run_regression_hardware.py `
  --create-baseline `
  --resource "TCPIP0::192.168.0.5::INSTR" `
  --baseline "hardware_verification_reports\baselines\dpo4054_tcpip_r0.json" `
  --output-dir "hardware_verification_reports\r0_probe_comp"
```

Compare against it with:

```powershell
python scripts/run_regression_hardware.py `
  --compare-baseline `
  --resource "TCPIP0::192.168.0.5::INSTR" `
  --baseline "hardware_verification_reports\baselines\dpo4054_tcpip_r0.json" `
  --output-dir "hardware_verification_reports\r0_probe_comp"
```

Thresholds can be overridden when there is a reviewed engineering reason:

```powershell
python scripts/run_regression_hardware.py `
  --compare-baseline `
  --resource "TCPIP0::192.168.0.5::INSTR" `
  --relative-limit 1.30 `
  --case-absolute-tolerance-s 0.25 `
  --total-absolute-tolerance-s 2.0 `
  --output-dir "hardware_verification_reports\r0_probe_comp"
```

Threshold changes should be reviewed rather than adjusted only to turn a failure into a pass.

## 8. USB versus TCPIP

Maintain separate hardware timing baselines for different transports. For example:

```text
baselines\dpo4054_tcpip_r0.json
baselines\dpo4054_usb_r0.json
```

Do not compare a TCPIP candidate against a USB baseline or vice versa. Transport latency is part of the hardware performance characteristic.

## 9. Output files

Every hardware repetition keeps its normal Automation/Logger HIL evidence under:

```text
<output-dir>\hil_runs\automation_logger_hil_<timestamp>\
```

and creates a diagnostic ZIP next to that directory.

A baseline comparison also writes:

```text
<output-dir>\comparisons\r0_hardware_compare_<timestamp>.json
<output-dir>\comparisons\r0_hardware_compare_<timestamp>.md
```

The command exits with code `0` when the regression comparison passes and `1` when it fails, so it can be used directly in a CI or release-qualification gate.

## 10. Recommended qualification sequence

For a significant change, run in this order:

```text
1. pytest -q
2. Ruff
3. single Probe Comp HIL run
4. --compare-baseline hardware regression
5. inspect comparison Markdown/JSON if any gate fails
6. for release or major session/logger changes, run the applicable 24 h / 72 h soak
```

Do not replace the reviewed R0 baseline until a performance/behavior change has been intentionally accepted and qualified.
