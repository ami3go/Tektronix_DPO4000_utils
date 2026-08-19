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
settings.py     JSON save/restore for Tektronix setup strings
hardcopy.py     PNG screen capture and SCPI block cleanup helpers
waveform.py     waveform acquisition and CSV export
channels.py     channel labels and simple measurements
trigger.py      acquisition and A-trigger helpers
instrument.py   DPO4000Scope / DPO4054 classes composed from mixins
```

## GUI modules

The GUI entry point is now separated from the main window implementation:

```text
gui/app.py          small public GUI entry point
gui/main_window.py  Tkinter main window implementation
gui/config.py       testable output-folder and filename helpers
gui/image_preview.py testable preview sizing helpers
gui/runner.py       console-script adapter for dpo4000-gui
```

The next GUI refactor step can migrate logic from `main_window.py` into these helper modules incrementally without changing the public entry point.

## Tests

Pure helper tests do not require a real oscilloscope:

```bash
pip install -e .[dev]
pytest -q
```

Hardware operations still require a connected scope and VISA runtime.

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
