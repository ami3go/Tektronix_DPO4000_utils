# dpo4000-utils and DPO4000 Desk

`dpo4000-utils` is a Python driver and automation toolkit for Tektronix DPO4000-family oscilloscopes, developed around the DPO4054.

**DPO4000 Desk** is the desktop GUI application built on top of `dpo4000-utils` for bench operation, screenshot capture, waveform export, measurement management, trigger control, and display setup.

The project provides:

- a reusable Python driver/API distributed as `dpo4000-utils`
- a stable Tkinter GUI through `dpo4000-gui`
- the modern desktop app through `dpo4000-desk`
- build scripts and GitHub Actions for Windows/Linux DPO4000 Desk executables

## DPO4000 Desk desktop GUI

![DPO4000 Desk GUI](docs/assets/titlebar-gui.png)

DPO4000 Desk uses a compact frameless titlebar layout with page buttons in the top row:

```text
Connection | Channels | Measurement | Trigger | Acquisition | File | Display | Log
```

Common front-panel style actions are available from the preview toolbar, including capture, copy, PNG export, CSV export, run/stop/single/continuous acquisition, and force trigger.

## Features

- USB/VISA and Ethernet VISA resource support.
- Short-lived VISA sessions so other scope software is not blocked while the GUI is idle.
- Screen capture as PNG with live preview.
- Copy captured screen to clipboard with `Ctrl+C`.
- Export enabled channel waveforms to CSV.
- Save and restore oscilloscope setup strings through SCPI.
- Read/write CH1..CH4 labels.
- Configure channel and MATH settings from DPO4000 Desk.
- Add, read, edit, and clear `MEAS1..MEAS8` measurement slots.
- Guarded measurement edit/delete mode to reduce accidental measurement deletion.
- Read/set trigger level and configure common edge-trigger options.
- Run, stop, single, continuous, and force-trigger controls.
- Dedicated File and Display pages for output and front-panel display settings.
- Persistent GUI preferences for connection resources, output folders, filenames, and trigger options.

## Install

Minimum Python:

```bash
python >= 3.10
```

Core driver plus Tkinter GUI:

```bash
python -m pip install -e .
```

DPO4000 Desk dependencies:

```bash
python -m pip install -e .[pyside6]
```

Development tools:

```bash
python -m pip install -e .[dev,pyside6]
```

Real instrument communication also requires a VISA runtime/backend such as NI-VISA, TekVISA, Keysight VISA, or a compatible PyVISA backend. PyVISA is the Python frontend; it does not replace the OS-level instrument driver stack.

## Run

Tkinter GUI:

```bash
dpo4000-gui
```

DPO4000 Desk:

```bash
dpo4000-desk
```

Direct module launch:

```bash
python -m dpo4000_utils.gui_qt.runner
```

## DPO4000 Desk first-run flow

1. Start `dpo4000-desk`.
2. Select **USB/VISA** or **Ethernet**.
3. Click **IDN** or **Retry** first.
4. After a successful `*IDN?`, protected scope actions unlock.
5. Use the top titlebar pages for setup: **Connection**, **Channels**, **Measurement**, **Trigger**, **Acquisition**, **File**, **Display**, and **Log**.
6. Use the preview toolbar for common capture/export/acquisition actions.

Useful shortcuts:

```text
F5              Capture preview
Ctrl+C          Copy preview after clicking the preview area
Ctrl+S          Save PNG
Ctrl+Shift+S    Save CSV
F6              Run acquisition
F7              Stop acquisition
F8              Single acquisition
Ctrl+L          Focus VISA resource field
Ctrl+1..8       Switch DPO4000 Desk pages
```

## Python API example

```python
from dpo4000_utils import DPO4054
from dpo4000_utils.control import MeasurementConfig

with DPO4054("USB0::0x0699::0x0401::C011280::INSTR", auto_connect=True) as scope:
    print(scope.scope.query("*IDN?").strip())
    print(scope.get_channel_labels())
    print(scope.get_trigger_level(channel=1))
    scope.add_measurement(MeasurementConfig(slot=1, measurement_type="FREQUENCY", source1="CH1"))
    scope.set_horizontal_position(0)
    scope.configure_edge_trigger(source="CH1", slope="RISE", coupling="DC", mode="AUTO", level="1.0")
```

Common API calls:

```python
scope.save_image_path("scope_screen.png")
scope.save_all_channels_to_single_csv("waveforms.csv")
scope.save_scope_settings("setup.json", ask_before_overwrite=False)
scope.apply_scope_settings("setup.json", wait_complete=False)
scope.set_channel_label(1, "INPUT")
scope.set_trigger_level(1.0, channel=1)
scope.read_measurement_value(1)
scope.disable_all_measurements()
scope.single_acquisition()
scope.force_trigger_event()
```

Legacy imports using `from tektronix_utils import DPO4054` remain supported.

## Build DPO4000 Desk executables

Windows `.exe`:

```bat
scripts\build_windows_exe.bat
```

Linux executable:

```bash
chmod +x scripts/build_linux_executable.sh
./scripts/build_linux_executable.sh
```

Default outputs:

```text
Windows: dist\DPO4000Desk\DPO4000Desk.exe
Linux:   dist/DPO4000Desk/DPO4000Desk
```

One-file builds:

```bash
BUILD_MODE=onefile scripts/build_linux_executable.sh
```

```powershell
$env:BUILD_MODE="onefile"
scripts\build_windows_exe.bat
```

The packaged GUI includes Python and collected Python packages, but the target PC still needs a VISA runtime/backend for real scope access.

See:

- `docs/build-application.md`
- `docs/build_executables.md`
- `docs/releases/v0.2.0.md`

## Tests

Pure/helper tests:

```bash
python -m pip install -e .[dev]
pytest -q
```

DPO4000 Desk metadata/runtime smoke checks:

```bash
python -m pip install -e .[dev,pyside6]
pytest -q tests/test_gui_qt_channel_config_metadata.py tests/test_gui_qt_runtime_smoke.py
```

Hardware tests are opt-in and require a connected DPO4000-family scope plus VISA runtime:

```bash
DPO4000_HARDWARE=1 \
DPO4000_RESOURCE='USB0::0x0699::0x0401::C011280::INSTR' \
pytest -q -m hardware tests/hardware
```

The optional label write/restore test is enabled only with `DPO4000_ENABLE_WRITE_TESTS=1`.

## GitHub Pages

The project page is built from `docs/` by `.github/workflows/pages.yml`.

After the workflow runs, the expected Pages URL is:

```text
https://ami3go.github.io/Tektronix_DPO4000_utils/
```

## Repository layout

```text
dpo4000_utils/               package code
dpo4000_utils/gui/           Tkinter GUI application
dpo4000_utils/gui_qt/        DPO4000 Desk desktop application
tektronix_utils.py           legacy compatibility import module
examples/                    small usage examples
scripts/                     helper scripts, including PyInstaller builds
docs/                        documentation and GitHub Pages site
tests/                       pure and opt-in hardware tests
archive/gui_versions/        old GUI snapshots kept for reference
```
