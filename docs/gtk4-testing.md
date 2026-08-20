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

## Why `pip install -e .[gtk]` failed on Windows

PyGObject is a Python binding over native GTK, GLib, GObject-Introspection, and related C libraries. A plain Python-only pip install on Windows often tries to build PyGObject from source and fails unless the full native GTK build/runtime toolchain is already installed.

For this reason the branch keeps the `gtk` extra empty. It is only a marker for this experimental GUI; GTK/PyGObject itself must come from the operating-system environment.

```powershell
py -3.13 -m pip install -e .[gtk]
```

This now installs the project and the `dpo4000-gui-gtk` command without trying to build PyGObject. Launching the command still requires a Python environment where `gi.repository.Gtk` is importable.

## Recommended Windows route: MSYS2 UCRT64

Install MSYS2, open the **UCRT64** shell, then install GTK4 and PyGObject from pacman:

```bash
pacman -Syu
pacman -S mingw-w64-ucrt-x86_64-python mingw-w64-ucrt-x86_64-python-pip mingw-w64-ucrt-x86_64-python-gobject mingw-w64-ucrt-x86_64-gtk4
```

From the MSYS2 UCRT64 shell, go to the checkout and install the project with the MSYS2 Python:

```bash
cd /c/Users/achestni/Documents/PycharmProjects/Libraries/Tektronix_DPO4000_utils
python -m pip install -e .
dpo4000-gui-gtk
```

Do not mix this with `C:\Program Files\Python313\python.exe`; use the MSYS2 Python for GTK testing.

## Linux route

On Debian/Ubuntu-style systems, install GTK4 and PyGObject from the distribution first:

```bash
sudo apt install python3-gi gir1.2-gtk-4.0
python3 -m pip install -e .
dpo4000-gui-gtk
```

Package names vary by distribution.

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
