"""Console entry point for the PySide6 GUI."""

from __future__ import annotations

import sys


def main() -> int:
    """Run the PySide6 GUI."""
    try:
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "PySide6 is not installed. Install the optional PySide6 GUI dependencies with:\n"
            "  python -m pip install -e .[pyside6]\n"
            "or:\n"
            "  python -m pip install -r requirements-pyside6.txt\n"
        ) from exc

    from .collapsible_window import QtScopeWindow
    from .startup_debug import install_startup_debug_probe, parse_startup_debug_args

    startup_debug = parse_startup_debug_args(sys.argv)
    app = QApplication(startup_debug.argv)
    debug_probe = None
    if startup_debug.enabled:
        debug_probe = install_startup_debug_probe(app, startup_debug.log_path)
        debug_probe.log("QApplication created")

    if debug_probe is not None:
        debug_probe.snapshot("before-window-construction")
    window = QtScopeWindow()
    if debug_probe is not None:
        debug_probe.log("QtScopeWindow constructed")
        debug_probe.snapshot("after-window-construction-before-show")

    window.show()
    if debug_probe is not None:
        debug_probe.log("main window show() called")
        debug_probe.snapshot("after-main-window-show")
        # Keep the probe alive for the whole application lifetime.
        app._dpo4000_startup_debug_probe = debug_probe  # type: ignore[attr-defined]

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
