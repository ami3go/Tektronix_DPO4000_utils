# dpo4000-utils / DPO4000 Desk

`dpo4000-utils` is a Python driver and automation toolkit for Tektronix DPO4000-family oscilloscopes, developed around the DPO4054.

**DPO4000 Desk** is the project's single desktop GUI. It is implemented with **PySide6** and acts as a presentation/orchestration layer over the public `dpo4000_utils` driver API.

## Architecture

```text
PySide6 DPO4000 Desk
        |
        v
GUI API adapter
        |
        v
scope_session()
        |
        v
DPO4054 / DPO4000Scope public API
        |
        v
PyVISA / VISA backend / oscilloscope
```

The GUI must not own SCPI commands, access the raw `scope.scope` VISA handle, parse hardcopy payloads, or implement waveform/settings transfer logic. Instrument behavior belongs in the reusable driver API.

See `docs/architecture.md` for the enforced boundary.

## Features

- PySide6 desktop application with Connection, Channels, Measurement, Trigger, Acquisition, File, Display, and Log pages.
- USB/VISA and Ethernet VISA resources.
- Short-lived driver-owned VISA sessions so other bench software is not blocked while the GUI is idle.
- PNG screen capture with preview and clipboard copy.
- Enabled-channel waveform export to CSV.
- Scope setup save/restore through JSON.
- CH1..CH4 labels and full channel configuration.
- MATH waveform configuration.
- MEAS1..MEAS8 measurement management.
- Trigger level and edge-trigger configuration.
- Run/stop/single/continuous acquisition and force trigger.
- Acquisition mode, averaging, and record-length controls.
- Front-panel display intensity, persistence, and message controls.
- Full real-hardware public API qualification with Markdown/HTML/JSON evidence reports.
- Windows/Linux PyInstaller build and release helpers.

## Install

Minimum Python version:

```text
Python 3.10+
```

Driver/API only:

```bash
python -m pip install -e .
```

Driver plus DPO4000 Desk:

```bash
python -m pip install -e .[pyside6]
```

Development environment with the desktop GUI:

```bash
python -m pip install -e .[dev,pyside6]
```

Real instrument communication also requires a VISA runtime/backend such as NI-VISA, TekVISA, Keysight VISA, or another backend supported by PyVISA.

## Run DPO4000 Desk

```bash
dpo4000-desk
```

Or directly from a repository checkout:

```bash
python -m dpo4000_utils.gui_qt.runner
```

Useful shortcuts:

```text
F5              Capture preview
Ctrl+C          Copy preview after focusing the preview
Ctrl+S          Save PNG
Ctrl+Shift+S    Save CSV
F6              Run acquisition
F7              Stop acquisition
F8              Single acquisition
Ctrl+L          Focus VISA resource field
Ctrl+1..8       Switch application pages
```

## Python API example

```python
from dpo4000_utils import AcquisitionConfig, ChannelConfig, DPO4054

with DPO4054(
    "USB0::0x0699::0x0401::C011280::INSTR",
    auto_connect=True,
) as scope:
    print(scope.query_identity())
    scope.configure_channel(ChannelConfig(channel=1, display=True, scale="0.5", coupling="DC"))
    scope.configure_acquisition(
        AcquisitionConfig(mode="AVERAGE", average_count=16, record_length="10k")
    )
    scope.save_image_path("scope_screen.png")
    scope.save_all_channels_to_single_csv("waveforms.csv")
```

For frontend-style short-lived sessions:

```python
from dpo4000_utils import scope_session

with scope_session(
    "TCPIP0::192.168.1.50::INSTR",
    timeout_ms=20_000,
) as scope:
    print(scope.query_identity())
```

## Build executables

Windows:

```bat
scripts\build_windows_exe.bat
```

Linux:

```bash
chmod +x scripts/build_linux_executable.sh
./scripts/build_linux_executable.sh
```

See `docs/build-application.md` and `docs/build_executables.md` for packaging details.

## Tests

Core tests:

```bash
python -m pip install -e .[dev]
pytest -q
```

Full desktop test environment:

```bash
python -m pip install -e .[dev,pyside6]
QT_QPA_PLATFORM=offscreen pytest -q
```

Focused hardware pytest tests remain opt-in:

```bash
DPO4000_HARDWARE=1 \
DPO4000_RESOURCE='USB0::0x0699::0x0401::C011280::INSTR' \
pytest -q -m hardware tests/hardware
```

## Full real-hardware qualification report

For release/bench qualification, use the self-auditing public API verifier. Start with the read-only profile:

```bash
python scripts/run_hardware_verification.py \
  --resource 'USB0::0x0699::0x0401::C011280::INSTR' \
  --profile read-only \
  --test-channel 1 \
  --waveform-points 1000
```

After the read-only run is clean, use `--profile reversible`, then `--profile full`. Write-capable profiles capture the initial scope setup and reapply it during final cleanup. Destructive REF waveform storage remains separately guarded and requires explicit overwrite authorization.

Each run generates Markdown, HTML, and JSON verification reports plus setup/screenshot/waveform evidence under `hardware_verification_reports/`.

See `docs/hardware-verification.md` for safety profiles, complete bench commands, exit-code semantics, waveform-size qualification, REF-overwrite handling, and self-hosted GitHub Actions usage.

## Repository layout

```text
dpo4000_utils/               reusable scope driver/API
dpo4000_utils/gui_qt/        PySide6 DPO4000 Desk application
dpo4000_utils/gui/           framework-neutral GUI support helpers/assets
examples/                    driver/API examples
scripts/                     build, packaging, and hardware-verification helpers
docs/                        documentation and GitHub Pages
tests/                       API, architecture, GUI, and hardware tests
```

The former Tk frontend and its archived snapshots were removed in v0.4.0. `dpo4000-desk` is the only desktop application command.
