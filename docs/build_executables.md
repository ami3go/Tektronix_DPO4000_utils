# Build GUI executables

The current application package target is the PySide6 GUI:

```text
dpo4000-gui-qt
  -> dpo4000_utils.gui_qt.runner.main
  -> dpo4000_utils.gui_qt.stable_window.QtScopeWindow
```

The build scripts use PyInstaller and should be run on the same operating system as the artifact you want to distribute:

- build Windows `.exe` artifacts on Windows
- build Linux artifacts on Linux

PyInstaller cross-compilation is not supported by these scripts.

The generated executable includes Python and collected Python packages, but it does **not** replace the system VISA runtime required to communicate with the oscilloscope.

## Recommended output mode

The default mode is `onedir` because it is more reliable for Qt applications and starts faster than `onefile`.

Default application name:

```text
TektronixDPO4000
```

Default outputs:

```text
Windows: dist\TektronixDPO4000\TektronixDPO4000.exe
Linux:   dist/TektronixDPO4000/TektronixDPO4000
```

Optional one-file outputs:

```text
Windows: dist\TektronixDPO4000.exe
Linux:   dist/TektronixDPO4000
```

## Windows `.exe`

From PowerShell or `cmd.exe` in the repository root:

```bat
scripts\build_windows_exe.bat
```

Compatibility alias:

```bat
scripts\build_exe.bat
```

One-file build:

```powershell
$env:BUILD_MODE="onefile"
scripts\build_windows_exe.bat
```

Custom app name:

```powershell
$env:APP_NAME="DPO4000Scope"
scripts\build_windows_exe.bat
```

Console/debug build:

```powershell
python scripts\build_app.py --mode onedir --console
```

## Linux executable

From a shell in the repository root:

```bash
chmod +x scripts/build_linux_executable.sh
./scripts/build_linux_executable.sh
```

One-file build:

```bash
BUILD_MODE=onefile scripts/build_linux_executable.sh
```

Custom app name:

```bash
APP_NAME=DPO4000Scope scripts/build_linux_executable.sh
```

Console/debug build:

```bash
python scripts/build_app.py --mode onedir --console
```

## Shared build helper

Both platform wrappers call:

```bash
python scripts/build_app.py --mode onedir --app-name TektronixDPO4000
```

Useful options:

```text
--mode onedir|onefile
--app-name NAME
--console
--skip-install
```

`--skip-install` is useful when the virtual environment already has the project and build dependencies installed.

The helper creates a small generated PyInstaller entry file under `build/pyinstaller_entry/` so package-relative imports behave like the installed `dpo4000-gui-qt` console script.

## Required runtime outside the executable

Real scope access still requires a VISA backend/runtime on the target PC, for example:

- NI-VISA
- TekVISA
- Keysight VISA
- a configured PyVISA backend suitable for your connection method

For USB instruments, install the relevant USB/VISA driver. For Ethernet/VXI-11 or raw socket access, make sure the target PC can reach the oscilloscope IP address.

## Smoke checks

Before packaging, test from source:

```bash
dpo4000-gui-qt
```

Run the Qt startup check:

```bash
python scripts/qt_startup_check.py
```

Run packaging metadata tests:

```bash
python -m pytest -q tests/test_build_scripts_metadata.py
```

## Manual GitHub Actions artifact build

If a workflow is configured, it should call the same scripts:

```text
scripts\build_windows_exe.bat
scripts/build_linux_executable.sh
```

Hardware is not required for packaging. VISA runtime is needed only when the generated app is used with a real oscilloscope.
