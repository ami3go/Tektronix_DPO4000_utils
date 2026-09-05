# Automation and Logger GUI Hardware-in-the-Loop Tests

This repository contains an opt-in pytest HIL suite for the final **DPO4000 Desk** PySide6 window. It exercises the Automation and Logger tabs against a real Tektronix DPO4000-family oscilloscope instead of a fake scope.

The suite is intentionally excluded from normal CI. It changes channel, trigger, acquisition, MATH and measurement setup and therefore requires an explicitly prepared bench.

## Supported bench topologies

### 1. Internal PROBE COMP stimulus

Connect the oscilloscope **PROBE COMP / calibration output to CH1**.

This topology qualifies:

- all seven Automation modes: Periodic Image, Image on Trigger, Image + CSV on Trigger, Timed Waveform Logging, Measurement Logger, Conditional Capture, and Burst Capture;
- Automation Start / Pause / Resume / Stop and run-limit behavior;
- Logger waveform records using CH1 and MATH;
- Logger Measurements using MEAS1..MEAS8;
- Logger Mixed mode without decoded BUS events;
- Logger CSV, DPO4LOG and CSV + DPO4LOG output;
- Logger Pause / Resume / Stop;
- bounded background writer behavior;
- count-based file rotation;
- ownership-based retention;
- runtime health counters;
- durable final run report;
- every value-bearing Automation/Logger GUI option through dynamic widget discovery.

The trigger test requires a *fresh* Single acquisition. A stale `SAVE` state is not accepted as success.

### 2. PicoScope 2206B signal-generator stimulus

Connect the **PicoScope 2206B AWG/signal-generator output to Tektronix CH1** and connect both instruments to the HIL computer over USB.

The test uses the PicoSDK `ps2000a` API and `ps2000aSetSigGenBuiltIn` to create sine, square and triangle signals. It verifies that the Tektronix scope measures the programmed frequency and peak-to-peak voltage, then uses the programmed signal to drive Conditional Automation and Mixed Logger capture.

PicoScope 2206B is a `ps2000a`-API device. The Python `picosdk` package is only the wrapper; the native PicoSDK / `ps2000a` driver must also be installed on the self-hosted runner.

Reference implementation and API documentation:

- https://github.com/picotech/picosdk-python-wrappers/blob/master/ps2000aExamples/ps2000aSigGen.py
- https://www.picotech.com/download/manuals/picoscope-2000-series-a-api-programmers-guide.pdf

## BUS Logger boundary

A PROBE COMP square wave or analog Pico AWG waveform cannot produce decoded I2C/SPI/CAN/RS-232 transactions. The HIL suite therefore covers the BUS Logger GUI option by verifying the existing hardware-capability gate:

- when decoded-event extraction is not hardware-qualified, Logger must refuse to start and must report the reason;
- if the connected scope reports decoded-event support, the transaction-level BUS test is skipped with a message that a dedicated serial-bus stimulus fixture is required.

The test deliberately does **not** invent undocumented BUS SCPI commands.

## Install

```bash
python -m pip install -e .[dev,hil]
```

For Pico tests, install Pico Technology's native PicoSDK/ps2000a driver for the runner operating system before running pytest.

## Environment gates

Common:

```bash
export DPO4000_HARDWARE=1
export DPO4000_GUI_HIL=1
export DPO4000_ENABLE_WRITE_TESTS=1
export DPO4000_RESOURCE='USB0::...::INSTR'
export QT_QPA_PLATFORM=offscreen
```

Probe-comp topology:

```bash
export DPO4000_PROBE_COMP_HIL=1
```

Optional tuning if a specific scope/probe-comp level requires it:

```bash
export DPO4000_PROBE_COMP_SCALE_VDIV=1.0
export DPO4000_PROBE_COMP_TRIGGER_V=0.5
```

PicoScope 2206B topology:

```bash
export DPO4000_PICO2206B_HIL=1
export PICO2206B_EXPECT_VARIANT=2206B
# Optional when multiple Pico devices are attached:
export PICO2206B_SERIAL='YOUR_SERIAL'
```

## Run locally

All GUI HIL tests:

```bash
pytest -ra -q -m 'hardware and gui_hil' tests/hardware/test_gui_automation_logger_hil.py
```

Probe-comp only:

```bash
pytest -ra -q -m 'probe_comp' tests/hardware/test_gui_automation_logger_hil.py
```

PicoScope 2206B only:

```bash
pytest -ra -q -m 'pico2206b' tests/hardware/test_gui_automation_logger_hil.py
```

## GitHub Actions

Use **Automation and Logger GUI HIL** from Actions and choose `probe-comp`, `pico2206b`, or `both`.

The runner must have labels `self-hosted` and `dpo4000`. For `pico2206b` or `both`, the native PicoSDK ps2000a library must be installed on that runner.

The workflow stores pytest temporary output under `hardware_verification_reports/gui-hil/` and uploads it even when a test fails.

## Safety and expected side effects

The suite:

- changes CH1 display/scale/coupling/probe gain;
- disables CH2..CH4 display during signal qualification;
- configures edge trigger on CH1;
- selects SAMPLE acquisition and a 1k record;
- configures MATH as CH1;
- configures MEAS1..MEAS8;
- creates image/CSV/DPO4LOG/report files in pytest temporary directories;
- returns acquisition to continuous mode when the scope fixture closes.

Run this only on a disposable/known HIL setup. Do not run it against a scope whose front-panel setup must remain untouched.

## Coverage philosophy

There are two complementary layers:

1. **GUI option traversal** dynamically discovers all value-bearing instance controls whose names start with `automation_` or `logger_`. Checkboxes are toggled, every combo-box item is selected, numeric controls visit minimum / midpoint / maximum, and text controls are round-tripped. The resulting Automation and Logger configurations must still pass their profile projection/preflight APIs.
2. **Operational HIL** runs every Automation mode and a matrix of Logger modes, sources and file formats against real signal hardware and verifies artifacts, writer state, health accounting and final reports.

The prefix-based traversal is intentional: adding a new Automation/Logger option to the final GUI makes the HIL inventory grow automatically instead of requiring a hand-maintained static list.
