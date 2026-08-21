"""Console entry point for the experimental PySide6 GUI."""

from __future__ import annotations

import sys


def main() -> int:
    """Run the experimental PySide6 GUI."""
    try:
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "PySide6 is not installed. Install the optional PySide6 GUI dependencies with:\n"
            "  python -m pip install -e .[pyside6]\n"
            "or:\n"
            "  python -m pip install -r requirements-pyside6.txt\n"
        ) from exc

    # Previous launched layer: from .acquisition_window import QtScopeWindow
    from .collapsible_window import QtScopeWindow

    app = QApplication(sys.argv)
    window = QtScopeWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
