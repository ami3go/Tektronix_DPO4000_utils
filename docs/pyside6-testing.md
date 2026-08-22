# DPO4000 Desk testing notes

DPO4000 Desk is the modern desktop application built on top of the `dpo4000-utils` Python driver.

The stable Tkinter GUI remains available with:

```bash
dpo4000-gui
```

DPO4000 Desk runs with:

```bash
pip install -e .[pyside6]
dpo4000-desk
```

or from the repository root:

```bash
pip install -e .[pyside6]
python -m dpo4000_utils.gui_qt.runner
```

## Current scope

DPO4000 Desk is now the main desktop workflow for bench use.

Implemented:

- Compact titlebar page layout.
- Left-side scope screen preview area.
- Pages: Connection, Channels, Measurement, Trigger, Acquisition, File, Display, Log.
- USB/VISA and Ethernet resource fields.
- IDN/retry connection flow.
- PNG capture and clipboard copy.
- CSV waveform export.
- Measurement add/read/edit/delete slot actions.
- Guarded measurement edit/delete mode.
- Trigger and acquisition actions: Run, Stop, Single, Continuous, Force trigger.
- Edge-trigger setup action.
- Horizontal position set action.
- Persistent GUI preferences.

## Test checklist

```text
1. Start dpo4000-desk.
2. Verify the titlebar page buttons switch pages.
3. Verify drag, maximize, minimize, close, and resize behavior.
4. Connect to the oscilloscope with USB/VISA or Ethernet.
5. Run IDN/retry.
6. Capture PNG and confirm the preview updates.
7. Save CSV from enabled channels.
8. Read, add, edit, and delete measurement slots.
9. Check trigger/acquisition actions on the real scope.
```
