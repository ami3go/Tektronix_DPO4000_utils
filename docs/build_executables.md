# Build GUI executables

The GUI can be packaged with PyInstaller for Windows and Linux. The generated executable includes Python and the Python packages, but it does **not** replace the system VISA runtime required to communicate with the oscilloscope.

## Windows `.exe`

From PowerShell or `cmd.exe` in the repository root:

```bat
scripts\build_windows_exe.bat
```

Compatibility alias:

```bat
scripts\build_exe.bat
```

Output:

```text
dist\TektronixScopeGUI.exe
```

The Windows build script uses:

```text
dpo4000_utils\gui\app.py
```

as the GUI entry point and includes package data from `dpo4000_utils`.

## Linux executable

From a shell in the repository root:

```bash
chmod +x scripts/build_linux_executable.sh
./scripts/build_linux_executable.sh
```

Output:

```text
dist/TektronixScopeGUI
```

On Debian/Ubuntu, install Tk support if your Python distribution does not include it:

```bash
sudo apt install python3-tk
```

## Required runtime outside the executable

The executable bundles Python code, but real scope access still requires a VISA backend/runtime on the target PC, for example:

- NI-VISA
- TekVISA
- Keysight VISA
- a configured PyVISA backend suitable for your connection method

## Manual GitHub Actions artifact build

A manual workflow named **Build GUI Executables** builds both artifacts:

- `TektronixScopeGUI-windows`
- `TektronixScopeGUI-linux`

The workflow does not run hardware tests and does not require a connected oscilloscope.
