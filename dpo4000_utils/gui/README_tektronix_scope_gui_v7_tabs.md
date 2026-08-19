# Tektronix DPO4054 GUI v7 - Tabbed Layout

This version reorganizes the GUI so buttons do not disappear below the visible screen area.

## Main layout

- Left side: auto-scaled oscilloscope screen preview.
- Right side: tabbed controls:
  - Channels
  - Trigger
  - Image / CSV
  - Settings
  - Log
- Bottom: compact status bar.

## Why this version exists

In v6, the preview and all control cards could exceed the vertical screen size on smaller monitors. The **Scope settings** buttons could appear below the visible window. In v7, the controls are moved into right-side tabs so the settings buttons are always reachable.

## Run

Put this file in the same folder as `tektronix_utils.py`, then run:

```bat
python tektronix_scope_gui_v7_tabs.py
```

or use:

```bat
run_tektronix_scope_gui_v7_tabs.bat
```

## Dependencies

Required:

```bat
pip install pyvisa
```

Optional, for higher-quality image preview scaling:

```bat
pip install pillow
```

You also need a VISA backend such as NI-VISA or TekVISA.

## Connection behavior

The GUI opens the VISA/USB connection only while a button operation is running, then closes it. This reduces the chance of blocking other scope software while the GUI is idle.
