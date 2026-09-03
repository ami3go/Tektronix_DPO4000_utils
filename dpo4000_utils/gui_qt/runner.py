"""Console entry point for the PySide6 DPO4000 Desk application."""
from __future__ import annotations
import sys
STARTUP_CHECK_FLAG="--startup-check"
def main()->int:
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError as exc: raise SystemExit("PySide6 is not installed. Install with `python -m pip install -e .[pyside6]`.") from exc
    from .logger_mixed_window import QtScopeWindow
    from .startup_debug import install_startup_debug_probe,parse_startup_debug_args
    debug=parse_startup_debug_args(sys.argv); startup=STARTUP_CHECK_FLAG in debug.argv
    app=QApplication([a for a in debug.argv if a!=STARTUP_CHECK_FLAG]); probe=install_startup_debug_probe(app,debug.log_path) if debug.enabled else None
    window=QtScopeWindow(); window.statusBar().showMessage("Ready. DPO4000 Desk (PySide6)."); window.show()
    if probe is not None: app._dpo4000_startup_debug_probe=probe  # type: ignore[attr-defined]
    if startup: QTimer.singleShot(2500,app.quit)
    return app.exec()
if __name__=="__main__": raise SystemExit(main())
__all__=["STARTUP_CHECK_FLAG","main"]
