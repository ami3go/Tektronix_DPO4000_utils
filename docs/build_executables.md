# Build DPO4000 Desk executables

The current application package target is the DPO4000 Desk desktop GUI:

```text
dpo4000-desk
```

DPO4000 Desk uses a frameless desktop window so the page buttons sit in the same row as the window title. The build scripts use PyInstaller and should be run on the same operating system as the artifact you want to distribute:

- build Windows `.exe` artifacts on Windows
- build Linux artifacts on Linux
- build Linux `.deb`, AppImage, and Flatpak bundle artifacts on Linux

PyInstaller cross-compilation is not supported by these scripts.

The generated executable includes Python and collected Python packages, but it does **not** replace the system VISA runtime required to communicate with the oscilloscope.

## Recommended output mode

The default mode is `onedir` because it starts faster and is easier to debug than `onefile`.

Default application name:

```text
DPO4000Desk
```

Default outputs:

```text
Windows: dist\DPO4000Desk\DPO4000Desk.exe
Linux:   dist/DPO4000Desk/DPO4000Desk
```

Optional one-file outputs:

```text
Windows: dist\DPO4000Desk.exe
Linux:   dist/DPO4000Desk
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
$env:APP_NAME="DPO4000DeskLab"
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
APP_NAME=DPO4000DeskLab scripts/build_linux_executable.sh
```

Console/debug build:

```bash
python scripts/build_app.py --mode onedir --console
```

## Linux `.deb`, AppImage, and Flatpak bundle

The Linux packaging helper consumes the one-file Linux binary at `dist/DPO4000Desk`:

```bash
BUILD_MODE=onefile scripts/build_linux_executable.sh
bash scripts/package_linux_release.sh
```

Expected local outputs:

```text
release-assets/DPO4000Desk-linux
release-assets/dpo4000-desk_0.2.0_amd64.deb
release-assets/DPO4000Desk-x86_64.AppImage
release-assets/DPO4000Desk.flatpak
```

The `.deb` package installs:

```text
/usr/bin/dpo4000-desk
/usr/share/applications/io.github.ami3go.DPO4000Desk.desktop
/usr/share/icons/hicolor/256x256/apps/io.github.ami3go.DPO4000Desk.png
/usr/share/metainfo/io.github.ami3go.DPO4000Desk.metainfo.xml
```

For local package builds, install the packaging tools first:

```bash
sudo apt-get install -y dpkg-dev desktop-file-utils flatpak flatpak-builder wget
```

For Flatpak bundle creation, add Flathub and install the runtime used by CI:

```bash
sudo flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
sudo flatpak install -y flathub org.freedesktop.Platform//24.08 org.freedesktop.Sdk//24.08
```

To create only the raw Linux binary, `.deb`, and AppImage:

```bash
BUILD_FLATPAK=0 bash scripts/package_linux_release.sh
```

## Shared build helper

Both platform wrappers call:

```bash
python scripts/build_app.py --mode onedir --app-name DPO4000Desk
```

Useful options:

```text
--mode onedir|onefile
--app-name NAME
--console
--skip-install
```

`--skip-install` is useful when the virtual environment already has the project and build dependencies installed.

The helper creates a small generated PyInstaller entry file under `build/pyinstaller_entry/` so package-relative imports behave like the installed `dpo4000-desk` console script.

## GitHub release assets

The workflow `.github/workflows/build-gui-executables.yml` builds one-file DPO4000 Desk assets for release:

```text
DPO4000Desk-windows.exe
DPO4000Desk-linux
dpo4000-desk_0.2.0_amd64.deb
DPO4000Desk-x86_64.AppImage
DPO4000Desk.flatpak
```

Create/update the `v0.2.0` release manually from GitHub Actions:

```text
Actions -> Build DPO4000 Desk Executables -> Run workflow
release_tag: v0.2.0
prerelease: false
```

Or publish by pushing the tag:

```bash
git tag v0.2.0
git push origin v0.2.0
```

The release body is sourced from `docs/releases/v0.2.0.md`.

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
dpo4000-desk
```

Run packaging metadata tests:

```bash
python -m pytest -q tests/test_build_scripts_metadata.py
```

Hardware is not required for packaging. VISA runtime is needed only when the generated app is used with a real oscilloscope.

The frameless title bar should be checked on target desktops: drag, double-click maximize, close/minimize/maximize controls, and resize behavior.
