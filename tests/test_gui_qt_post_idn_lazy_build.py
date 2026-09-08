from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from dpo4000_utils.gui_qt.composition.window import QtScopeWindow  # noqa: E402


def _app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([sys.executable, "qt-post-idn-test"])
    return app


def test_post_idn_scope_parameter_lazy_build_does_not_require_logger_prebuild() -> None:
    """Mirror Test IDN success -> refresh_scope_parameters() page-build precondition."""
    app = _app()
    window = QtScopeWindow()
    try:
        surface = window.feature_surface
        assert not hasattr(surface, "logger_mode_combo")
        surface._ensure_scope_parameter_pages_built()
        assert hasattr(surface, "logger_mode_combo")
        assert hasattr(surface, "logger_channel_checks")
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
