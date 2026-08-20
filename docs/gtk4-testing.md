# GTK4 testing branch

This branch adds an experimental GTK4 / PyGObject GUI beside the existing Tkinter GUI.

The normal Tkinter command remains unchanged:

```bash
dpo4000-gui
```

The experimental GTK4 command is:

```bash
dpo4000-gui-gtk
```

## Install notes

GTK4/PyGObject usually needs system packages in addition to Python package metadata.
On Linux, install your distribution's GTK4, GObject introspection, and PyGObject packages first.
Then install this project with the optional GTK extras:

```bash
pip install -e .[gtk]
dpo4000-gui-gtk
```

On Windows, PyGObject/GTK4 is usually easiest through an MSYS2 GTK environment rather than a plain Python-only pip install. Treat this branch primarily as a Linux-native comparison prototype.

## Current GTK4 prototype scope

Implemented for comparison:

- Dark GTK4 CSS theme.
- Left screen preview area.
- Right-side tabs: Connection, Channels, Measurement, Trigger, Settings, Log.
- Test IDN.
- Capture preview.
- Copy preview to clipboard through GTK/GDK texture clipboard.
- Add/read/clear measurement slots.
- Trigger run/stop/single/continuous/force actions.
- Set trigger level.
- Set horizontal trigger position.
- Apply common edge-trigger setup.

Still intentionally incomplete:

- Full channel label UI.
- Persistent preferences.
- CSV export controls.
- Settings save/restore controls.
- Build/packaging scripts.
- Hardware-tested GTK event-loop behavior.

## Windows caution

This branch is meant for visual and architecture comparison. GTK4 can run on Windows, but packaging and dependency setup are more complex than PySide6. For a production Windows desktop app, PySide6 is still likely the lower-risk path.
