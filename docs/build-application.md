# Build DPO4000 Desk

This guide builds the current DPO4000 Desk desktop application entry point:

```text
dpo4000-desk
  -> dpo4000_utils.gui_qt.runner.main
  -> dpo4000_utils.gui_qt.titlebar_tabs_window.QtScopeWindow
```

DPO4000 Desk uses a frameless desktop window so the page buttons can share the same row as the window title. Build on the same operating system you want to distribute for:

- build the Windows `.exe` on Windows
- build the Linux executable on Linux

Cross-compiling with PyInstaller is not supported by these scripts.

## Output format

Default output mode is `onedir` because it starts faster and is easier to debug than `onefile`.

Default application name:

```text
DPO4000Desk
```

Default outputs:

```text
Windows: dist\DPO4000Desk\DPO4000Desk.exe
Linux:   dist/DPO4000Desk/DPO4000Desk
```

Optional `onefile` outputs:

```text
Windows: dist\DPO4000Desk.exe
Linux:   dist/DPO4000Desk
```

## Windows build

From the repository root:

```powershell
git checkout main
git pull
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
scripts\build_windows_exe.bat
```

Validate arguments without running PyInstaller:

```powershell
scripts\build_windows_exe.bat --dry-run --skip-install
```

Build one-file `.exe` instead:

```powershell
$env:BUILD_MODE="onefile"
scripts\build_windows_exe.bat
```

Use a custom executable name:

```powershell
$env:APP_NAME="DPO4000DeskLab"
scripts\build_windows_exe.bat
```

Debug a startup failure with console output:

```powershell
python scripts\build_app.py --mode onedir --console
```

## Linux build

From the repository root:

```bash
git checkout main
git pull
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
chmod +x scripts/build_linux_executable.sh
scripts/build_linux_executable.sh
```

Validate arguments without running PyInstaller:

```bash
scripts/build_linux_executable.sh --dry-run --skip-install
```

Use an explicit Python executable if `python3` is not the active virtual environment:

```bash
PYTHON=.venv/bin/python scripts/build_linux_executable.sh
```

Build one-file executable instead:

```bash
BUILD_MODE=onefile scripts/build_linux_executable.sh
```

Use a custom executable name:

```bash
APP_NAME=DPO4000DeskLab scripts/build_linux_executable.sh
```

Debug a startup failure with console output:

```bash
python scripts/build_app.py --mode onedir --console
```

## Shared build helper

Both wrappers call the shared Python helper:

```bash
python scripts/build_app.py --mode onedir --app-name DPO4000Desk
```

Useful options:

```text
--mode onedir|onefile
--app-name NAME
--console
--skip-install
--dry-run
--no-clean
```

`--skip-install` is useful when your virtual environment already has the project and build dependencies installed. `--dry-run` prints the resolved PyInstaller command and output path without modifying the environment or running PyInstaller.

## Release workflow

The GitHub Actions workflow `.github/workflows/build-gui-executables.yml` can build one-file DPO4000 Desk release assets and create a GitHub release.

Expected release assets:

```text
DPO4000Desk-windows.exe
DPO4000Desk-linux
```

Manual release from GitHub Actions:

```text
Actions -> Build DPO4000 Desk Executables -> Run workflow
release_tag: v0.2.0
prerelease: false
```

Command-line release by tag push:

```bash
git checkout main
git pull
git tag v0.2.0
git push origin v0.2.0
```

The workflow publishes the release body from:

```text
docs/releases/v0.2.0.md
```

## Test before packaging

Run the app from source first:

```bash
dpo4000-desk
```

Run packaging metadata tests:

```bash
python -m pytest -q tests/test_build_scripts_metadata.py
```

## Runtime requirements on the target PC

The packaged application includes the Python code and PyInstaller-collected dependencies, but real instrument communication still needs a VISA runtime/backend installed on the target machine.

Typical choices:

```text
NI-VISA
TekVISA
Keysight VISA
compatible pyvisa backend
```

For USB instruments, install the relevant USB/VISA driver. For Ethernet/VXI-11 or socket access, make sure the target PC can reach the oscilloscope IP address.

## Notes

- `onedir` is recommended for daily use and debugging.
- `onefile` is convenient for transfer but starts slower because it extracts files at launch.
- Build Windows packages on Windows and Linux packages on Linux.
- The frameless title bar should be checked on target desktops: drag, maximize, close, and resize behavior.
- The old `scripts/build_exe.bat` remains as a compatibility wrapper for `scripts/build_windows_exe.bat`.
