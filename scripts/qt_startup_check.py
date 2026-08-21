"""Run the PySide6 GUI briefly with startup diagnostics enabled.

Usage from the repository root:

    python scripts/qt_startup_check.py

The script opens the GUI, records startup top-level widget events, closes the GUI
after a short delay, and prints the log path.  It is intended for Windows startup
flicker checks without needing manual close/copy steps.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


LOG_PATH = Path("qt_startup_debug.log")


def main() -> int:
    command = [
        sys.executable,
        "-m",
        "dpo4000_utils.gui_qt.runner",
        "--startup-debug",
        f"--startup-debug-log={LOG_PATH}",
        "--startup-check",
    ]
    result = subprocess.run(command, check=False)
    print(f"Qt startup check finished with exit code {result.returncode}")
    print(f"Startup log: {LOG_PATH.resolve()}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
