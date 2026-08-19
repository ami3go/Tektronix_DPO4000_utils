# Tektronix DPO4000 Utilities

Python utilities and a Tkinter GUI for Tektronix DPO4000-family oscilloscopes, developed around the DPO4054.

## Features

- USB/VISA and Ethernet VISA resource support.
- Read and write CH1..CH4 channel labels.
- Capture the scope screen as PNG and preview it in the GUI.
- Export enabled channel waveform data to CSV.
- Save and restore oscilloscope settings through Tektronix SCPI setup strings.
- Set and read A trigger level from the GUI.
- Short-lived VISA sessions in the GUI so other scope software is not blocked while idle.
- Persistent GUI preferences for last-used resources, output folders, naming settings, and trigger options.

## Requirements

Python dependencies are installed by the package:

```bash
pip install -e .
```

For real instrument communication, the PC still needs a VISA runtime/driver installed, for example NI-VISA, TekVISA, or Keysight VISA. PyVISA is the Python frontend; it does not replace the instrument USB/Ethernet driver stack.

## Run the GUI

From a checkout:

```bash
pip install -e .
dpo4000-gui
```

or:

```bash
python -m dpo4000_utils.gui
```

## Basic script usage

```python
from dpo4000_utils import DPO4054

with DPO4054(auto_connect=True) as scope:
    print(scope.scope.query("*IDN?").strip())
```

Legacy scripts that use `from tektronix_utils import DPO4054` are supported by the top-level compatibility module.

## Driver modules

The driver is split into focused modules while keeping the public `DPO4054` API compatible:

```text
connection.py   VISA session lifecycle and USB/Ethernet resource helpers
settings.py     JSON save/restore helpers, setup validation, and restore error handling
hardcopy.py     PNG screen capture, SCPI block cleanup, validation, and file save helpers
waveform.py     waveform acquisition, scaling, enabled-channel discovery, and CSV export
channels.py     channel labels and simple measurements
trigger.py      acquisition and A-trigger helpers
instrument.py   DPO4000Scope / DPO4054 classes composed from mixins
```

The GUI screenshot path uses `hardcopy.py`, the GUI settings restore path uses `settings.py`, and the GUI CSV export path uses `waveform.py`, so transfer, validation, scaling, and diagnostic behavior are shared between scripts and the GUI.

## GUI modules

The active GUI now has a flattened public class plus extracted panel builders:

```text
gui/app.py              public GUI entry point; exports ScopeGui
gui/scope_gui.py        active flattened ScopeGui class
gui/base_window.py      historical base window implementation
gui/main_window.py      compatibility shim for older imports
gui/connection_panel.py extracted Connection tab builder
gui/channels_panel.py   extracted Channels tab builder
gui/trigger_panel.py    extracted Trigger tab builder
gui/settings_panel.py   extracted Settings tab builder
gui/preview_panel.py    extracted preview and image/CSV action builder
gui/log_panel.py        extracted Log tab builder
gui/runner.py           console-script and python -m entry point
gui/config.py           output folder and filename generation helpers
gui/connection_ui.py    connection resource, timeout, and trigger form validation helpers
gui/image_preview.py    preview sizing/subsampling helpers
gui/preferences.py      persistent GUI preference load/save helpers
```

Compatibility wrappers from the incremental refactor are still present (`stateful_window.py`, `waveform_window.py`, and `sectioned_window.py`), but the public entry point now imports `scope_gui.ScopeGui` directly. The previous monolithic `main_window.py` has been retired to a compatibility shim; the historical base implementation lives in `base_window.py` until the remaining core window lifecycle and job-running code is slimmed further.

## Tests

Pure helper tests do not require a real oscilloscope:

```bash
pip install -e .[dev]
pytest -q
```

Hardware API tests are opt-in and require a connected DPO4000-family scope plus a VISA runtime:

```bash
DPO4000_HARDWARE=1 \
DPO4000_RESOURCE='USB0::0x0699::0x0401::C011280::INSTR' \
pytest -q -m hardware tests/hardware
```

The hardware suite checks connection, `*IDN?`, channel-label read API, trigger-level read API, and SCPI status access. A label write/restore test is available only when `DPO4000_ENABLE_WRITE_TESTS=1` is set. See `docs/hardware-api-tests.md` for bench setup and the manual self-hosted GitHub Actions workflow.

GitHub Actions runs the pure test suite on Python 3.10, 3.11, 3.12, and 3.13 for pushes and pull requests targeting `main`. Hardware tests are run only by the manual `Hardware API Tests` workflow on a self-hosted runner with access to the oscilloscope.

## Build a Windows executable

```bat
scripts\build_exe.bat
```

The generated EXE includes Python and Python packages, but target PCs still need a VISA runtime installed to access the oscilloscope.

## Repository layout

```text
src/dpo4000_utils/           package code
src/dpo4000_utils/gui/       active GUI application
examples/                    small usage examples
scripts/                     helper scripts, including PyInstaller build
docs/                        usage and troubleshooting notes
tests/                       pure helper tests without hardware dependency
archive/gui_versions/        old GUI snapshots kept for reference
```
