from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtCore = pytest.importorskip("PySide6.QtCore")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from dpo4000_utils.gui_qt.composition.services import (  # noqa: E402
    LogController,
    OutputPathController,
    PageController,
    PreferencesController,
    ScopeDispatchController,
    WindowChromeController,
)
from dpo4000_utils.gui_qt.composition.window import QtScopeWindow  # noqa: E402


def _app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([sys.executable, "qt-composition-test"])
    return app


def test_composed_window_has_shallow_mro_and_embeds_feature_surface():
    app = _app()
    window = QtScopeWindow()
    try:
        assert QtScopeWindow.__bases__ == (QtWidgets.QMainWindow,)
        assert window.centralWidget() is window.feature_surface
        assert window.feature_surface.parent() is window
        assert window.windowFlags() & QtCore.Qt.WindowType.FramelessWindowHint
        assert window.windowTitle() == window.feature_surface.windowTitle()
        assert window.preview_label is window.feature_surface.preview_label
        assert window.control_stack is window.feature_surface.control_stack
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_composed_window_routes_cross_cutting_services_through_controllers():
    app = _app()
    window = QtScopeWindow()
    try:
        surface = window.feature_surface
        assert isinstance(window.scope_controller, ScopeDispatchController)
        assert isinstance(window.page_controller, PageController)
        assert isinstance(window.log_controller, LogController)
        assert isinstance(window.output_controller, OutputPathController)
        assert isinstance(window.preferences_controller, PreferencesController)
        assert isinstance(window.window_chrome, WindowChromeController)

        assert surface._run_action.__self__ is window.scope_controller
        assert surface._select_drawer_page.__self__ is window.page_controller
        assert surface._append_log.__self__ is window.log_controller
        assert surface._build_output_path.__self__ is window.output_controller
        assert surface._save_preferences_safely.__self__ is window.preferences_controller
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_composed_page_controller_preserves_lazy_page_behavior():
    app = _app()
    window = QtScopeWindow()
    try:
        window.page_controller.select(4)
        assert window.page_controller.current_index == 4
        assert window._lazy_control_pages_built[4] is True
        assert window.current_page_title.text() == "Acquisition"
        assert hasattr(window, "acquisition_mode")
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
