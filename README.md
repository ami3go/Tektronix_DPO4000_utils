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

scope = DPO4054(auto_connect=True)
try:
    print(scope.scope.query("*IDN?").strip())
finally:
    scope.disconnect()
```

Legacy scripts that use `from tektronix_utils import DPO4054` are supported by the top-level compatibility module.

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
archive/gui_versions/        old GUI snapshots kept for reference
```
