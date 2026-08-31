from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from dpo4000_utils.gui_qt.display_window import DISPLAY_PAGE_INDEX, FILE_PAGE_INDEX  # noqa: E402
from dpo4000_utils.gui_qt.ui_polish_window import QtScopeWindow  # noqa: E402


def _app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([sys.executable, "ui-polish-test"])
    return app


def _button_texts(window) -> set[str]:
    return {button.text() for button in window.findChildren(QtWidgets.QAbstractButton)}


def test_file_page_builds_folder_open_and_scope_settings_actions():
    app = _app()
    window = QtScopeWindow()
    try:
        window._select_drawer_page(FILE_PAGE_INDEX)
        texts = _button_texts(window)
        assert {"Folder", "Open", "Save", "Restore", "Default"} <= texts
        assert "Pick folder" not in texts
        assert hasattr(window, "output_folder")
        assert hasattr(window, "settings_prefix")
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_requested_cards_use_short_read_apply_clear_labels():
    app = _app()
    window = QtScopeWindow()
    try:
        window._select_drawer_page(1)
        texts = _button_texts(window)
        assert "Read labels" not in texts
        assert "Apply labels" not in texts
        assert {"Read", "Apply"} <= texts

        window._select_drawer_page(4)
        texts = _button_texts(window)
        assert "Read acquisition setup" not in texts
        assert "Apply acquisition setup" not in texts
        assert {"Read", "Apply"} <= texts

        window._select_drawer_page(DISPLAY_PAGE_INDEX)
        texts = _button_texts(window)
        assert "Read display" not in texts
        assert "Apply display" not in texts
        assert "Clear text" not in texts
        assert {"Read", "Apply", "Clear"} <= texts
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
