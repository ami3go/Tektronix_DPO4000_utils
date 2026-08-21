"""Build the DPO4000 PySide6 application with PyInstaller.

The script intentionally creates a tiny generated entry-point file instead of
passing ``dpo4000_utils/gui_qt/runner.py`` directly to PyInstaller.  That keeps
package-relative imports working the same way they do when running the installed
``dpo4000-gui-qt`` console script.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP_NAME = "TektronixDPO4000"
ENTRY_DIR = ROOT / "build" / "pyinstaller_entry"
ENTRY_FILE = ENTRY_DIR / "dpo4000_qt_entry.py"
ICON_FILE = ROOT / "dpo4000_utils" / "gui" / "dpo_scope_icon.ico"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the DPO4000 PySide6 GUI package.")
    parser.add_argument(
        "--app-name",
        default=os.environ.get("APP_NAME", DEFAULT_APP_NAME),
        help=f"Executable/application name. Default: {DEFAULT_APP_NAME}",
    )
    parser.add_argument(
        "--mode",
        choices=("onedir", "onefile"),
        default=os.environ.get("BUILD_MODE", "onedir"),
        help="PyInstaller output mode. 'onedir' starts faster and is easier to debug; 'onefile' is portable but slower to start.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        default=os.environ.get("BUILD_CLEAN", "1") not in {"0", "false", "False"},
        help="Remove build/dist output before building. Enabled by default.",
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="Keep a console window. Useful for debugging PyInstaller startup errors.",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Do not install/upgrade build dependencies before running PyInstaller.",
    )
    return parser.parse_args()


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def clean_outputs(app_name: str) -> None:
    for path in (ROOT / "build", ROOT / "dist"):
        if path.exists():
            shutil.rmtree(path)
    for spec in ROOT.glob(f"{app_name}*.spec"):
        spec.unlink()


def write_entry_file() -> None:
    ENTRY_DIR.mkdir(parents=True, exist_ok=True)
    ENTRY_FILE.write_text(
        "from dpo4000_utils.gui_qt.runner import main\n"
        "raise SystemExit(main())\n",
        encoding="utf-8",
    )


def install_build_dependencies() -> None:
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", "-e", ".[build,pyside6]"])


def pyinstaller_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        args.app_name,
    ]

    if args.mode == "onefile":
        command.append("--onefile")
    else:
        command.append("--onedir")

    command.append("--console" if args.console else "--windowed")

    if platform.system() == "Windows" and ICON_FILE.exists():
        command.extend(["--icon", str(ICON_FILE)])

    command.extend(
        [
            "--collect-all",
            "dpo4000_utils",
            "--collect-all",
            "PySide6",
            "--collect-all",
            "pyvisa",
            "--collect-all",
            "PIL",
            "--hidden-import",
            "dpo4000_utils.gui_qt.runner",
            "--hidden-import",
            "dpo4000_utils.gui_qt.stable_window",
            "--hidden-import",
            "dpo4000_utils.gui_qt.scope_worker",
            "--hidden-import",
            "dpo4000_utils.gui_qt.startup_debug",
            str(ENTRY_FILE),
        ]
    )
    return command


def output_hint(app_name: str, mode: str) -> str:
    system = platform.system()
    if system == "Windows":
        if mode == "onefile":
            return f"dist\\{app_name}.exe"
        return f"dist\\{app_name}\\{app_name}.exe"
    if mode == "onefile":
        return f"dist/{app_name}"
    return f"dist/{app_name}/{app_name}"


def main() -> int:
    args = parse_args()
    print(f"Building {args.app_name} for {platform.system()} ({args.mode})", flush=True)
    if args.clean:
        clean_outputs(args.app_name)
    write_entry_file()
    if not args.skip_install:
        install_build_dependencies()
    run(pyinstaller_command(args))

    output = output_hint(args.app_name, args.mode)
    print("\nBuild finished:", output)
    print("Target machine still needs a VISA runtime/backend for real instrument access.")
    print("Examples: NI-VISA, TekVISA, Keysight VISA, or a compatible pyvisa backend.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
