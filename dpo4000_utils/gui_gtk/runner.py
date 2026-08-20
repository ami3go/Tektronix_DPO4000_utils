"""Console-script entry point for the experimental GTK4 GUI."""

from __future__ import annotations

import sys


GTK_IMPORT_HELP = """
GTK4/PyGObject is not available in this Python environment.

On Windows, do not expect `pip install PyGObject` to work with the normal
python.org interpreter. Use one of these routes instead:

1. MSYS2 UCRT64 GTK environment:
   pacman -S mingw-w64-ucrt-x86_64-python mingw-w64-ucrt-x86_64-python-gobject mingw-w64-ucrt-x86_64-gtk4
   python -m pip install -e .
   dpo4000-gui-gtk

2. Linux / WSL / VM:
   install python3-gi and GTK4 packages from the distribution package manager,
   then run this branch there.

For Windows production comparison, the PySide6 branch is expected to be easier.
""".strip()


def main() -> None:
    """Run the experimental GTK4 GUI."""
    try:
        from .main_window import run
    except (ImportError, ModuleNotFoundError) as exc:
        print(GTK_IMPORT_HELP, file=sys.stderr)
        print(f"\nOriginal import error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    raise SystemExit(run())


if __name__ == "__main__":
    main()


__all__ = ["GTK_IMPORT_HELP", "main"]
