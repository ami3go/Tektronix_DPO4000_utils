"""Build the DPO4000 PySide6 application with PyInstaller.

The script intentionally creates a tiny generated entry-point file instead of
passing ``dpo4000_utils/gui_qt/runner.py`` directly to PyInstaller. That keeps
package-relative imports working the same way they do when running the installed
``dpo4000-gui-qt`` console script.
"""

from __future__ import annotations

import argparse
import os
import platform
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP_NAME = "TektronixDPO4000"
ENTRY_DIR = ROOT / "build" / "pyinstaller_entry"
ENTRY_FILE = ENTRY_DIR / "dpo4000_qt_entry.py"
ICON_FILE = ROOT / "dpo4000_utils" / "gui" / "dpo_scope_icon.ico"
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}
BUILD_MODES = ("onedir", "onefile")
UNSAFE_APP_NAME_CHARS = {"/", "\\", ":"}


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalised = value.strip().lower()
    if normalised in TRUE_VALUES:
        return True
    if normalised in FALSE_VALUES:
        return False
    return default


def _validate_app_name(parser: argparse.ArgumentParser, app_name: str) -> None:
    if not app_name.strip():
        parser.error("--app-name cannot be empty")
    if any(character in app_name for character in UNSAFE_APP_NAME_CHARS):
        parser.error("--app-name cannot contain path separators or drive separators")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the DPO4000 PySide6 GUI package.")
    parser.add_argument(
        "--app-name",
        default=os.environ.get("APP_NAME", DEFAULT_APP_NAME),
        help=f"Executable/application name. Default: {DEFAULT_APP_NAME}",
    )
    parser.add_argument(
        "--mode",
        choices=BUILD_MODES,
        default=os.environ.get("BUILD_MODE", "onedir"),
        help=(
            "PyInstaller output mode. 'onedir' starts faster and is easier to debug; "
            "'onefile' is portable but slower to start."
        ),
    )
    parser.add_argument(
        "--clean",
        action=argparse.BooleanOptionalAction,
        default=_env_flag("BUILD_CLEAN", default=True),
        help="Remove build/dist output before building. Enabled by default; pass --no-clean to keep existing output.",
    )
    parser.add_argument(
        "--console",
        action="store_true",
        default=_env_flag("BUILD_CONSOLE", default=False),
        help="Keep a console window. Useful for debugging PyInstaller startup errors.",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        default=_env_flag("BUILD_SKIP_INSTALL", default=False),
        help="Do not install/upgrade build dependencies before running PyInstaller.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved PyInstaller command and output path without running it.",
    )
    args = parser.parse_args()
    _validate_app_name(parser, args.app_name)
    return args


def format_command(command: list[str]) -> str:
    """Return a shell-readable command for logging without changing execution."""
    return " ".join(shlex.quote(part) for part in command)


def run(command: list[str], *, dry_run: bool = False) -> None:
    print("+", format_command(command), flush=True)
    if not dry_run:
        subprocess.run(command, cwd=ROOT, check=True)


def clean_outputs(app_name: str, *, dry_run: bool = False) -> None:
    targets = [ROOT / "build", ROOT / "dist", *ROOT.glob(f"{app_name}*.spec")]
    for path in targets:
        if dry_run:
            print(f"Would remove: {path.relative_to(ROOT)}")
            continue
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def write_entry_file(*, dry_run: bool = False) -> None:
    content = "from dpo4000_utils.gui_qt.runner import main\nraise SystemExit(main())\n"
    if dry_run:
        print(f"Would write generated entry: {ENTRY_FILE.relative_to(ROOT)}")
        print(content.rstrip())
        return
    ENTRY_DIR.mkdir(parents=True, exist_ok=True)
    ENTRY_FILE.write_text(content, encoding="utf-8")


def install_build_dependencies(*, dry_run: bool = False) -> None:
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], dry_run=dry_run)
    run([sys.executable, "-m", "pip", "install", "-e", ".[build,pyside6]"], dry_run=dry_run)


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
            "dpo4000_utils.gui_qt.preview_window",
            "--hidden-import",
            "dpo4000_utils.gui_qt.measurement_window",
            "--hidden-import",
            "dpo4000_utils.gui_qt.display_window",
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


def output_path(app_name: str, mode: str) -> Path:
    if platform.system() == "Windows":
        if mode == "onefile":
            return ROOT / "dist" / f"{app_name}.exe"
        return ROOT / "dist" / app_name / f"{app_name}.exe"
    if mode == "onefile":
        return ROOT / "dist" / app_name
    return ROOT / "dist" / app_name / app_name


def output_hint(app_name: str, mode: str) -> str:
    return str(output_path(app_name, mode).relative_to(ROOT))


def verify_output_exists(app_name: str, mode: str) -> None:
    output = output_path(app_name, mode)
    if not output.exists():
        raise SystemExit(
            f"PyInstaller finished but expected output was not found: {output.relative_to(ROOT)}"
        )
    if output.is_dir():
        raise SystemExit(f"Expected executable path is a directory: {output.relative_to(ROOT)}")


def main() -> int:
    args = parse_args()
    print(f"Building {args.app_name} for {platform.system()} ({args.mode})", flush=True)
    if args.clean:
        clean_outputs(args.app_name, dry_run=args.dry_run)
    write_entry_file(dry_run=args.dry_run)
    if not args.skip_install:
        install_build_dependencies(dry_run=args.dry_run)
    command = pyinstaller_command(args)
    run(command, dry_run=args.dry_run)

    output = output_hint(args.app_name, args.mode)
    if not args.dry_run:
        verify_output_exists(args.app_name, args.mode)
    print("\nBuild finished:" if not args.dry_run else "\nDry run output would be:", output)
    print("Target machine still needs a VISA runtime/backend for real instrument access.")
    print("Examples: NI-VISA, TekVISA, Keysight VISA, or a compatible pyvisa backend.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
