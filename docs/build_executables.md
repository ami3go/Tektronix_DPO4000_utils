# Build DPO4000 Desk executables

The desktop package target is:

```text
dpo4000-desk
```

DPO4000 Desk is packaged with PyInstaller. Build Windows artifacts on Windows and Linux artifacts on Linux; these scripts do not cross-compile PyInstaller applications.

The generated application includes Python and collected Python packages, but **does not replace the system VISA runtime** required for real oscilloscope communication.

## Reproducible v0.7 release environment

Normal project dependency metadata remains range-based for downstream users. Official release builds additionally use:

```text
constraints-release.txt
```

which pins the tested release/build/runtime toolchain. The GitHub release workflow installs through this file and stores the resolved `pip freeze` output with each platform artifact. This gives every shipped binary an auditable dependency environment.

For a local release-equivalent environment:

```bash
python -m pip install -c constraints-release.txt -e '.[build,pyside6]'
```

For development/testing:

```bash
python -m pip install -c constraints-release.txt -e '.[dev,pyside6]'
```

## Recommended output mode

`onedir` is the normal Windows release mode because it starts faster and is easier to diagnose than a single self-extracting executable.

Default application name:

```text
DPO4000Desk
```

Typical outputs:

```text
Windows: dist\DPO4000Desk\DPO4000Desk.exe
Linux:   dist/DPO4000Desk/DPO4000Desk
```

## Windows build

```bat
scripts\build_windows_exe.bat
```

Compatibility alias:

```bat
scripts\build_exe.bat
```

One-file local build:

```powershell
$env:BUILD_MODE="onefile"
scripts\build_windows_exe.bat
```

Console/debug build:

```powershell
python scripts\build_app.py --mode onedir --console
```

The release workflow compresses the Windows application folder as `DPO4000Desk-windows.zip`.

## Linux executable and packages

Build executable:

```bash
chmod +x scripts/build_linux_executable.sh
./scripts/build_linux_executable.sh
```

One-file executable:

```bash
BUILD_MODE=onefile scripts/build_linux_executable.sh
```

Package `.deb`, AppImage and Flatpak artifacts:

```bash
BUILD_MODE=onefile scripts/build_linux_executable.sh
bash scripts/package_linux_release.sh
```

Expected release assets include:

```text
release-assets/DPO4000Desk-linux
release-assets/dpo4000-desk_0.7.0_amd64.deb
release-assets/DPO4000Desk-x86_64.AppImage
release-assets/DPO4000Desk.flatpak
```

Linux packaging prerequisites used by CI include `dpkg-dev`, `desktop-file-utils`, `flatpak`, `flatpak-builder`, and the Freedesktop 24.08 runtime/SDK.

## Shared build helper

Platform wrappers ultimately use:

```bash
python scripts/build_app.py --mode onedir --app-name DPO4000Desk
```

Useful switches:

```text
--mode onedir|onefile
--app-name NAME
--console
--skip-install
```

`--skip-install` is appropriate only when the current environment was already prepared with the required constrained dependencies.

## GitHub release workflow

`.github/workflows/build-gui-executables.yml` builds the Windows and Linux assets. For v0.7.0, run it manually with:

```text
Actions -> Build DPO4000 Desk Executables -> Run workflow
release_tag: v0.7.0
prerelease: false
```

or push the corresponding tag after the release commit is on `main`:

```bash
git tag v0.7.0
git push origin v0.7.0
```

The release body is sourced from `docs/releases/v0.7.0.md`.

## Required runtime outside the executable

Real scope access still requires an installed VISA backend/runtime such as NI-VISA, TekVISA, Keysight VISA, or another PyVISA-compatible backend. USB targets additionally need the corresponding USB/VISA driver; Ethernet targets need network reachability to the oscilloscope.

## Pre-release checks

Run normal tests and lint:

```bash
python -m pytest -q
ruff check dpo4000_utils tests scripts tektronix_utils.py
```

Run packaging metadata tests:

```bash
python -m pytest -q tests/test_build_scripts_metadata.py
```

Hardware is not required to create packages, but packaged-app communication must still be verified on a target PC with a VISA stack. Hardware API/soak qualification is documented separately in `docs/hardware-verification.md`.
