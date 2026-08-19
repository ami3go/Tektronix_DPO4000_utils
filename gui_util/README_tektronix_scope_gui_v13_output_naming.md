# Tektronix DPO4054 GUI v13 - Output folder and naming settings

## What changed

The **Settings** tab now includes output controls:

- Destination folder entry
- **Pick folder** button
- Separate filename settings for:
  - PNG images
  - CSV waveforms
  - Scope settings JSON
- Per-file-type prefix field
- Per-file-type base/constant filename field
- Per-file-type timestamp checkbox

Final filename format:

```text
<prefix><base><_YYYYMMDD_HHMMSS if timestamp is enabled>.<extension>
```

Examples:

```text
scope_screen_20260819_111200.png
scope_waveform_20260819_111200.csv
dpo4054_setup_20260819_111200.json
```

If timestamp is disabled and the file already exists, the GUI asks before overwriting.

## Save behavior

PNG, CSV, and settings JSON are now saved directly to the configured destination folder. The GUI no longer asks for a full save path for these actions.

## Run

```bat
python tektronix_scope_gui_v13_output_naming.py
```

## Build EXE

```bat
build_exe_v13_output_naming.bat
```

A VISA runtime such as NI-VISA, TekVISA, or Keysight VISA is still required on the measurement PC for USB/LAN instrument communication.
