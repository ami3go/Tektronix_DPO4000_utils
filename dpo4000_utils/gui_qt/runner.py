"""Console entry point for the experimental PySide6 GUI."""

from __future__ import annotations

import sys


def main() -> int:
    """Run the experimental PySide6 GUI."""
    try:
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "PySide6 is not installed. Install the optional Qt GUI dependencies with:\n"
            "  pip install -e .[qt]\n"
        ) from exc

    from .main_window import QtScopeWindow

    app = QApplication(sys.argv)
    window = QtScopeWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
