# Automation + Logger Probe Comp HIL

This bench runner qualifies the DPO4000 Desk Automation and Logger data paths against a real DPO4000-family oscilloscope using the scope's own Probe Comp square-wave output as repeatable stimulus.

## Fixture

1. Connect the DPO4054 `PROBE COMP` signal to CH1 with a normal high-impedance probe/input.
2. Do not use 50 ohm termination on the Probe Comp output.
3. Close DPO4000 Desk and other VISA clients before starting the runner.
4. The runner saves the current `*LRN?` setup, temporarily configures CH1, a 1k-point record, edge triggering, MEAS1=FREQUENCY and MEAS2=PK2PK, then reapplies the saved setup at the end.

The default preflight expects a roughly 1 kHz Probe Comp waveform and intentionally uses broad functional limits rather than calibration-grade limits.

## Run the complete bench suite

PowerShell:

```powershell
git fetch
git switch test/automation-logger-hil
git pull

python scripts/run_automation_logger_hil.py `
  --resource "TCPIP0::192.168.0.5::INSTR" `
  --channel 1 `
  --suite all `
  --output-dir "hardware_verification_reports\automation_logger_hil"
```

The runner exits with code 0 when no case fails and code 1 when any case fails. A SKIP is not a failure.

Useful subsets:

```powershell
# Automation only
python scripts/run_automation_logger_hil.py --resource "TCPIP0::192.168.0.5::INSTR" --suite automation

# Logger only, without slow hardcopy operations
python scripts/run_automation_logger_hil.py --resource "TCPIP0::192.168.0.5::INSTR" --suite logger --skip-hardcopy
```

## Coverage

Automation cases exercise A1 through A12 where the Probe Comp fixture can provide meaningful hardware evidence: periodic image, fresh-Single image, image+CSV bundle, timed waveform CSV, measurement logging, conditional capture, burst capture, run limits, retention, profiles, reconnect primitives and durable reporting.

Logger cases exercise waveform, measurement, mixed fresh-Single and MATH sources; CSV and DPO4LOG output; segment rotation; the bounded queue and real writer thread; health accounting; reconnect primitives; profiles; retention; checkpoint/final reporting. Decoded BUS event logging is reported as SKIP because Probe Comp -> CH1 is not serial-bus stimulus and decoded BUS extraction is not hardware-qualified by the current driver.

A11/recovery performs a controlled disconnect/reconnect smoke test. It does not unplug a cable, disable Ethernet, or intentionally corrupt a live VISA transport. Physical transport-fault injection remains a separate manual qualification step.

## Diagnostic bundle

Every case runs independently. A failure does not prevent later independent cases from running unless the initial Probe Comp fixture itself is invalid.

The run directory contains:

- `hil_run.log` - chronological case and hardware-state log, including raw `ACQUIRE:STATE?` and `TRIGGER:STATE?` preflight responses.
- `hil_report.json` - machine-readable results and environment metadata.
- `hil_report.md` - human-readable summary.
- `environment.json` - Python/platform/package versions.
- `tracebacks/` - complete traceback for every failed case.
- `artifacts/` - generated PNG, CSV, DPO4LOG, profile, retention and report evidence.
- `scope_setup_before.json` and `scope_setup_after_restore.json` - setup restoration evidence.

At the end the runner prints the path to a `*_diagnostic_bundle.zip`. Upload that ZIP to ChatGPT for debugging.

## Options

Use `python scripts/run_automation_logger_hil.py --help` for the complete list. Important options include `--trigger-timeout-s`, `--waveform-points`, `--expected-frequency-hz`, `--frequency-tolerance`, `--min-vpp`, `--max-vpp`, and `--skip-hardcopy`.
