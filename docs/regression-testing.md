# Regression testing runbook

This runbook covers the executable R0 software regression tests and the real-hardware DPO4000 Probe Comp regression baseline.

## Bench connection

For hardware regression, connect the oscilloscope front-panel **PROBE COMP** output to **CH1** with the probe ground connected to the Probe Comp ground point.

```text
DPO4054 PROBE COMP  --->  CH1 probe tip
DPO4054 GND         --->  CH1 probe ground
```

Do not use 50-ohm termination for this fixture. The regression runner configures CH1, trigger, measurements, and record length, then restores the original scope setup at the end of every HIL repetition.

## Optional SCPI preflight

The runner performs its own setup, so these commands are not required. They are useful for manually confirming that the VISA connection and Probe Comp signal are healthy before a regression run.

```text
*IDN?
SELECT:CH1 ON
CH1:COUPLING DC
HORIZONTAL:RECORDLENGTH 1000
TRIGGER:A:TYPE EDGE
TRIGGER:A:EDGE:SOURCE CH1
TRIGGER:A:EDGE:SLOPE RISE
TRIGGER:A:EDGE:COUPLING DC
TRIGGER:A:MODE NORMAL
TRIGGER:A:LEVEL:CH1 1.0
MEASUREMENT:MEAS1:TYPE FREQUENCY
MEASUREMENT:MEAS1:SOURCE1 CH1
MEASUREMENT:MEAS1:STATE ON
MEASUREMENT:MEAS2:TYPE PK2PK
MEASUREMENT:MEAS2:SOURCE1 CH1
MEASUREMENT:MEAS2:STATE ON
MEASUREMENT:MEAS1:VALUE?
MEASUREMENT:MEAS2:VALUE?
```

With the DPO4054 Probe Comp output, expect approximately 1 kHz and roughly 2.5 Vpp. The automated preflight uses configurable tolerances and does not require the exact nominal values.

## One-command batch orchestrator

`scripts/run_regression_batch.py` is the primary orchestration entry point. It discovers every `tests/test_regression_*.py` file automatically and also runs:

- `tests/test_hardware_regression.py`
- `tests/test_persistent_scope_stress.py`
- `tests/test_logger_stress.py`

The hardware stage is optional. The orchestrator stops before hardware if the software regression stage fails unless `--continue-after-software-failure` is explicitly supplied.

### Software regression only

PowerShell / Linux:

```powershell
python scripts/run_regression_batch.py
```

Windows batch wrapper:

```bat
scripts\run_regression_batch.bat
```

To run the entire pytest suite instead of only regression/stress files:

```powershell
python scripts/run_regression_batch.py --all-tests
```

## Create the first real-hardware R0 baseline

Use this only after the DPO4054 Probe Comp output is connected to CH1 and the software regression stage is passing.

```powershell
python scripts/run_regression_batch.py `
  --hardware create `
  --resource "TCPIP0::192.168.0.5::INSTR" `
  --channel 1 `
  --suite all `
  --repetitions 5 `
  --output-dir "hardware_verification_reports\r0_probe_comp"
```

Equivalent Windows batch wrapper:

```bat
scripts\run_regression_batch.bat --hardware create --resource "TCPIP0::192.168.0.5::INSTR" --channel 1 --suite all --repetitions 5 --output-dir "hardware_verification_reports\r0_probe_comp"
```

The default baseline path is:

```text
hardware_verification_reports/r0_probe_comp/r0_hardware_baseline.json
```

Creation refuses to overwrite an existing baseline. To intentionally replace a reviewed baseline:

```powershell
python scripts/run_regression_batch.py `
  --hardware create `
  --resource "TCPIP0::192.168.0.5::INSTR" `
  --force-baseline
```

Review the new baseline JSON before treating it as the authoritative R0 performance reference.

## Compare a future build with the R0 baseline

```powershell
python scripts/run_regression_batch.py `
  --hardware compare `
  --resource "TCPIP0::192.168.0.5::INSTR" `
  --channel 1 `
  --suite all `
  --output-dir "hardware_verification_reports\r0_probe_comp"
```

The comparison uses the baseline repetition count by default. A different count can be requested explicitly with `--repetitions`, although matching the baseline count gives the cleanest p95/p99 comparison.

Default performance gates are:

```text
p95 relative limit:          1.30x (+30%)
per-case absolute tolerance: 0.25 s
whole-run absolute tolerance: 2.0 s
```

A timing case fails only when the candidate exceeds both the relative and absolute limits. Functional case/status mismatches fail independently of timing.

## Generated evidence

Each hardware repetition keeps its normal HIL diagnostic bundle. The hardware comparison additionally writes JSON and Markdown comparison reports. The top-level orchestrator writes:

```text
hardware_verification_reports/r0_probe_comp/regression_batch_summary.json
```

Exit code `0` means every requested stage passed. A non-zero exit code means at least one requested regression stage failed or was prevented from running by a prior failure.

## Separate baselines by transport

Do not compare TCPIP and USB timing directly. The hardware baseline records the VISA resource family and the compare command fails if the transport family changes. Keep separate reviewed baselines for TCPIP and USB if both interfaces are qualified.
