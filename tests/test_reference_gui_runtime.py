from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from dpo4000_utils.gui_qt.desktop_window import QtScopeWindow  # noqa: E402


def _app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([sys.executable, "reference-gui-smoke-test"])
    return app


def test_channels_page_builds_reference_waveform_controls():
    app = _app()
    window = QtScopeWindow()
    try:
        window._select_drawer_page(1)

        assert hasattr(window, "reference_channel")
        assert [window.reference_channel.itemText(index) for index in range(4)] == [
            "1",
            "2",
            "3",
            "4",
        ]
        assert hasattr(window, "reference_display")
        assert hasattr(window, "reference_label")
        assert hasattr(window, "reference_vertical_scale")
        assert hasattr(window, "reference_vertical_position")
        assert hasattr(window, "reference_horizontal_scale")
        assert hasattr(window, "reference_horizontal_delay")
        assert window.reference_stored_at.isReadOnly()
        sources = [
            window.reference_source.itemText(index)
            for index in range(window.reference_source.count())
        ]
        assert sources == [
            "CH1",
            "CH2",
            "CH3",
            "CH4",
            "MATH",
            "REF1",
            "REF2",
            "REF3",
            "REF4",
        ]
        assert window._callback_requires_scope(window.read_reference_configuration)
        assert window._callback_requires_scope(window.apply_reference_configuration)
        assert window._callback_requires_scope(window.store_reference_waveform)
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_reference_snapshot_projection_follows_selected_ref():
    app = _app()
    window = QtScopeWindow()
    try:
        window._select_drawer_page(1)
        window._scope_parameter_snapshot = {
            "references": {
                1: {
                    "display": "ON",
                    "label": "Golden",
                    "vertical_scale": "0.1",
                    "vertical_position": "1.0",
                    "horizontal_scale": "4E-6",
                    "horizontal_delay": "2E-6",
                    "date": "28-AUG-2026",
                    "time": "10:00:00",
                },
                2: {
                    "display": "OFF",
                    "label": "Limit",
                    "vertical_scale": "0.2",
                    "vertical_position": "-1.0",
                    "horizontal_scale": "8E-6",
                    "horizontal_delay": "0",
                    "date": "27-AUG-2026",
                    "time": "09:00:00",
                },
            }
        }

        window.reference_channel.setCurrentText("1")
        window._apply_cached_reference_configuration()
        assert window.reference_display.isChecked()
        assert window.reference_label.text() == "Golden"
        assert window.reference_stored_at.text() == "28-AUG-2026 10:00:00"

        window.reference_channel.setCurrentText("2")
        window._apply_cached_reference_configuration()
        assert not window.reference_display.isChecked()
        assert window.reference_label.text() == "Limit"
        assert window.reference_vertical_scale.text() == "0.2"
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
