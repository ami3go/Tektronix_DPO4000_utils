"""Console entry point for the PySide6 DPO4000 Desk application."""

from __future__ import annotations

import sys

STARTUP_CHECK_FLAG = "--startup-check"


def main() -> int:
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "PySide6 is not installed. Install with `python -m pip install -e .[pyside6]` "
            "or `python -m pip install -r requirements-pyside6.txt`."
        ) from exc

    from .production_hardening_window import QtScopeWindow as ProductionHardenedQtScopeWindow
    from .milestone_a_window import QtScopeWindow
    from .startup_debug import install_startup_debug_probe, parse_startup_debug_args

    # Milestone A is deliberately a thin final shell above the reviewed production
    # hardening layer; v0.8 will replace the historical chain with composition.
    if not issubclass(QtScopeWindow, ProductionHardenedQtScopeWindow):
        raise RuntimeError("Milestone-A window must extend the production hardening window")

    startup_debug = parse_startup_debug_args(sys.argv)
    startup_check = STARTUP_CHECK_FLAG in startup_debug.argv
    app = QApplication([arg for arg in startup_debug.argv if arg != STARTUP_CHECK_FLAG])
    debug_probe = (
        install_startup_debug_probe(app, startup_debug.log_path)
        if startup_debug.enabled
        else None
    )
    if debug_probe is not None:
        debug_probe.snapshot("before-window-construction")
    window = QtScopeWindow()
    if debug_probe is not None:
        debug_probe.snapshot("after-window-construction-before-show")
    window.statusBar().showMessage("Ready. DPO4000 Desk (PySide6).")
    window.show()
    if debug_probe is not None:
        debug_probe.snapshot("after-main-window-show")
        app._dpo4000_startup_debug_probe = debug_probe  # type: ignore[attr-defined]
    if startup_check:
        QTimer.singleShot(2500, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["STARTUP_CHECK_FLAG", "main"]
