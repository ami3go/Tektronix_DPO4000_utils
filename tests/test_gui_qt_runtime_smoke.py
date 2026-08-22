from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from dpo4000_utils.gui_qt.collapsible_window import WINDOW_TITLE  # noqa: E402
from dpo4000_utils.gui_qt.display_window import (  # noqa: E402
    CONTROL_PAGE_BUILDERS,
    DISPLAY_PAGE_INDEX,
    FILE_PAGE_INDEX,
)
from dpo4000_utils.gui_qt.measurement_window import QtScopeWindow  # noqa: E402


def _app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([sys.executable, "qt-smoke-test"])
    return app


def test_stable_qt_window_constructs_with_lazy_pages():
    app = _app()
    window = QtScopeWindow()
    try:
        assert window.windowTitle() == WINDOW_TITLE
        assert window.control_stack.count() == len(CONTROL_PAGE_BUILDERS)
        assert len(window._lazy_control_pages_built) == len(CONTROL_PAGE_BUILDERS)
        assert window._lazy_control_pages_built[0] is True
        assert sum(bool(value) for value in window._lazy_control_pages_built) == 1
        assert window.current_page_title.text() == "Connection"
        assert window.main_splitter.handleWidth() == 12
        top_level_titles = {widget.windowTitle() for widget in app.topLevelWidgets() if widget.isVisible()}
        assert top_level_titles <= {"", WINDOW_TITLE}
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_stable_qt_lazy_page_builds_on_selection():
    app = _app()
    window = QtScopeWindow()
    try:
        window._select_drawer_page(4)
        assert window._lazy_control_pages_built[4] is True
        assert window.current_page_title.text() == "Acquisition"
        assert hasattr(window, "acquisition_mode")
        assert hasattr(window, "acquisition_record_length")
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_measurement_page_builds_existing_measurement_manager():
    app = _app()
    window = QtScopeWindow()
    try:
        window._select_drawer_page(2)
        assert window._lazy_control_pages_built[2] is True
        assert window.current_page_title.text() == "Measurement"
        assert hasattr(window, "existing_measurements")
        assert window.existing_measurements.rowCount() == 8
        assert window.existing_measurements.columnCount() == 6
        assert hasattr(window, "measurement_slot")
        assert hasattr(window, "measurement_type")
        assert hasattr(window, "measurement_source1")
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_file_page_keeps_file_output_settings_without_display_controls():
    app = _app()
    window = QtScopeWindow()
    try:
        window._select_drawer_page(FILE_PAGE_INDEX)
        assert window._lazy_control_pages_built[FILE_PAGE_INDEX] is True
        assert window.current_page_title.text() == "File"
        assert hasattr(window, "output_folder")
        assert hasattr(window, "png_prefix")
        assert not hasattr(window, "display_backlight")
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_display_page_builds_display_controls():
    app = _app()
    window = QtScopeWindow()
    try:
        window._select_drawer_page(DISPLAY_PAGE_INDEX)
        assert window._lazy_control_pages_built[DISPLAY_PAGE_INDEX] is True
        assert window.current_page_title.text() == "Display"
        assert hasattr(window, "display_backlight")
        assert hasattr(window, "display_persistence")
        assert hasattr(window, "display_message_text")
        assert hasattr(window, "display_message_state")
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_stable_qt_worker_metadata_is_present():
    content = Path("dpo4000_utils/gui_qt/stable_window.py").read_text(encoding="utf-8")
    worker = Path("dpo4000_utils/gui_qt/scope_worker.py").read_text(encoding="utf-8")

    assert "QEventLoop" in content
    assert "start_scope_worker" in content
    assert "_run_snapshot_scope_session" in content
    assert "DPO4054(resource, auto_connect=False)" in content
    assert "instrument.timeout = timeout_ms" in content
    assert "class ScopeWorker(QRunnable)" in worker
    assert "QThreadPool.globalInstance().start(worker)" in worker
