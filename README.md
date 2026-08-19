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

or directly from the repository root:

```bash
python -m dpo4000_utils.gui
```

The package now uses a root package layout: `dpo4000_utils/` is directly in the repository root. There is no `src/` folder. This keeps direct Windows commands such as `pytest` and `python -m dpo4000_utils.gui` simpler from a checkout.

## Interaction guide

### GUI interaction flow

1. **Select connection mode**
   - Use **USB/VISA** for a discovered local VISA resource such as `USB0::0x0699::0x0401::C011280::INSTR`.
   - Use **Ethernet** for a TCPIP resource generated from host, protocol, and port fields.
   - Click **Refresh resources** to re-scan VISA resources.
   - Click **Connect / IDN** to open a short-lived session and read `*IDN?`.

2. **Work with channel labels**
   - Use the Channels tab to read CH1..CH4 labels from the scope.
   - Edit a label field and apply it to write the corresponding `CHn:LABEL` setting.
   - Label changes are direct hardware writes.

3. **Capture screen and waveform data**
   - Click **Capture PNG** to read a scope hardcopy and save it to the configured output folder.
   - The GUI preview updates from the saved PNG.
   - Click **Save CSV** to export all enabled channel waveforms into one CSV file.
   - The CSV path uses the shared waveform driver helpers, including enabled-channel detection and voltage scaling.

4. **Use trigger controls**
   - Read or set A trigger level from the Trigger tab.
   - Trigger level accepts numeric volts and supported presets such as `TTL` or `ECL`.
   - Optional re-arm behavior after image capture can be enabled in the settings.

5. **Save and restore scope setup**
   - Click **Save settings** to store the current scope setup as JSON.
   - Click **Restore settings** to apply a saved JSON setup file back to the scope.
   - Restore can optionally wait for `*OPC?`, but this may time out on some older DPO4000 firmware even when the setup has applied.

6. **Configure output and preferences**
   - Choose the output folder and filename prefixes/base names in the Settings tab.
   - GUI preferences are persisted automatically after edits and again on window close.
   - Stored preferences include resource selection, Ethernet settings, timeout, output folder, naming options, and trigger options.

### Script/API interaction flow

Use the driver directly when you want automation without the GUI:

```python
from dpo4000_utils import DPO4054

with DPO4054("USB0::0x0699::0x0401::C011280::INSTR", auto_connect=True) as scope:
    print(scope.scope.query("*IDN?").strip())
    print(scope.get_channel_labels())
    print(scope.get_trigger_level(channel=1))
```

Common API interactions:

```python
scope.save_image_path("scope_screen.png")
scope.save_all_channels_to_single_csv("waveforms.csv")
scope.save_scope_settings("setup.json", ask_before_overwrite=False)
scope.apply_scope_settings("setup.json", wait_complete=False)
scope.set_channel_label(1, "INPUT")
scope.set_trigger_level(1.0, channel=1)
```

### Hardware test interaction flow

The hardware API tests are skipped unless explicitly enabled. The default hardware suite is read-mostly and checks connection, `*IDN?`, channel-label reads, trigger-level reads, and `*ESR?` status access.

Recommended Windows PowerShell setup from a checkout:

```powershell
py -3.13 -m pip install --upgrade pip
py -3.13 -m pip install -e .[dev]
$env:DPO4000_HARDWARE = "1"
$env:DPO4000_RESOURCE = "USB0::0x0699::0x0401::C011280::INSTR"
py -3.13 -m pytest -q -m hardware tests/hardware
```

Direct `pytest` from a checkout also works because `dpo4000_utils/` is now a root-level package:

```powershell
$env:DPO4000_HARDWARE = "1"
$env:DPO4000_RESOURCE = "USB0::0x0699::0x0401::C011280::INSTR"
pytest -q -m hardware tests/hardware
```

Editable install is still recommended before normal development because it also verifies package metadata and console scripts.

Linux/macOS shell equivalent:

```bash
DPO4000_HARDWARE=1 \
DPO4000_RESOURCE='USB0::0x0699::0x0401::C011280::INSTR' \
pytest -q -m hardware tests/hardware
```

The optional label write/restore test changes one channel label, verifies it, and restores the previous value. Enable it only on a bench scope where this is acceptable:

```powershell
$env:DPO4000_HARDWARE = "1"
$env:DPO4000_ENABLE_WRITE_TESTS = "1"
$env:DPO4000_TEST_CHANNEL = "1"
$env:DPO4000_RESOURCE = "USB0::0x0699::0x0401::C011280::INSTR"
py -3.13 -m pytest -q -m hardware tests/hardware
```

The manual GitHub Actions workflow named **Hardware API Tests** is intended for a self-hosted runner connected to the oscilloscope and labeled `self-hosted` and `dpo4000`.

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
dpo4000_utils/               package code
dpo4000_utils/gui/           active GUI application
tektronix_utils.py           legacy compatibility import module
examples/                    small usage examples
scripts/                     helper scripts, including PyInstaller build
docs/                        usage and troubleshooting notes
tests/                       pure and opt-in hardware tests
archive/gui_versions/        old GUI snapshots kept for reference
```
