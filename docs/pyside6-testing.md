# PySide6 testing branch

This branch contains an experimental PySide6/Qt GUI beside the existing Tkinter GUI.

The current stable Tkinter GUI is unchanged and still runs with:

```bash
dpo4000-gui
```

The experimental Qt GUI runs with:

```bash
pip install -e .[qt]
dpo4000-gui-qt
```

or from the repository root:

```bash
pip install -e .[qt]
python -m dpo4000_utils.gui_qt.runner
```

## Current scope

This is a first testing pass, not a full replacement yet.

Implemented in the Qt prototype:

- Dark Qt stylesheet matching the current application theme.
- Left-side scope screen preview area.
- Right-side tabs: Connection, Channels, Measurement, Trigger, Settings, Log.
- Connection tab with USB/VISA and Ethernet resource fields.
- `Test IDN` action.
- Preview capture to `scope_output/qt_preview.png`.
- Copy captured preview to the system clipboard through Qt.
- Measurement add/read/clear slot actions.
- Trigger acquisition actions: Run, Stop, Single, Continuous, Force trigger.
- Edge-trigger setup action.
- Horizontal position set action.

Still incomplete compared with the Tk GUI:

- Channel label read/write is only scaffolded.
- CSV waveform export is scaffolded.
- Settings save/restore is scaffolded.
- Preferences persistence is not implemented.
- Long-running hardware operations are synchronous in this first pass.

## Design rule

Keep `dpo4000_utils/gui_qt/` separate from `dpo4000_utils/gui/` until the Qt GUI is stable enough to replace the Tk GUI.
