from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from dpo4000_utils.gui_qt.bus_window import QtScopeWindow  # noqa: E402
from dpo4000_utils.gui_qt.desktop_window import (  # noqa: E402
    CONNECTION_TEST_DESCRIPTION,
    QtScopeWindow as DesktopQtScopeWindow,
)


def _app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([sys.executable, "bus-runtime-test"])
    return app


def test_connection_page_has_read_all_parameters_option_enabled_by_default():
    app = _app()
    window = QtScopeWindow()
    try:
        assert hasattr(window, "read_all_parameters_after_connection")
        assert window.read_all_parameters_after_connection.isChecked() is True
        assert "Read all parameters after connection" == (
            window.read_all_parameters_after_connection.text()
        )
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_connection_checkbox_controls_automatic_parameter_refresh(monkeypatch):
    app = _app()
    window = QtScopeWindow()
    refresh_calls: list[str] = []
    try:
        monkeypatch.setattr(
            window,
            "_run_action",
            lambda description, callback: (
                "TEKTRONIX,DPO4054,C000001,CF:91.1" if description == CONNECTION_TEST_DESCRIPTION else None
            ),
        )
        monkeypatch.setattr(
            DesktopQtScopeWindow,
            "refresh_scope_parameters",
            lambda self: refresh_calls.append("refresh"),
        )

        window.read_all_parameters_after_connection.setChecked(False)
        window.test_connection()
        assert refresh_calls == []
        assert "parameter read skipped" in window.statusBar().currentMessage()

        window.read_all_parameters_after_connection.setChecked(True)
        window.test_connection()
        assert refresh_calls == ["refresh"]
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_final_desktop_channels_page_builds_all_four_bus_channels_and_protocol_table():
    app = _app()
    window = QtScopeWindow()
    try:
        window._ensure_control_page_built(1)
        assert [window.bus_channel.itemText(i) for i in range(window.bus_channel.count())] == [
            "1",
            "2",
            "3",
            "4",
        ]
        bus_types = {window.bus_type.itemText(i) for i in range(window.bus_type.count())}
        assert {
            "I2C",
            "SPI",
            "CAN",
            "RS232C",
            "LIN",
            "FLEXRAY",
            "AUDIO",
            "USB",
            "PARALLEL",
        } <= bus_types

        window.bus_type.setCurrentText("SPI")
        labels = {
            window.bus_protocol_table.item(row, 0).text()
            for row in range(window.bus_protocol_table.rowCount())
        }
        assert "MISO Source" in labels
        assert "MOSI Source" in labels
        assert "SS Source" in labels
        assert window.bus_protocol_table.rowCount() == 12
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_final_desktop_applies_cached_bus_snapshot_on_bus_selection():
    app = _app()
    window = QtScopeWindow()
    try:
        window._ensure_control_page_built(1)
        snapshot = {
            "labels": {},
            "channels": {},
            "references": {},
            "buses": {
                1: {
                    "state": "1",
                    "type": "I2C",
                    "label": "ECU",
                    "position": "-1",
                    "display_format": "HEXADECIMAL",
                    "display_type": "BUS",
                    "protocol": {"clock_source": "CH1", "data_source": "CH2"},
                },
                2: {
                    "state": "0",
                    "type": "CAN",
                    "label": "Vehicle CAN",
                    "position": "2",
                    "display_format": "HEXADECIMAL",
                    "display_type": "BOTH",
                    "protocol": {"bit_rate": "500000", "source": "CH3"},
                },
            },
            "math": {},
            "measurements": {},
            "trigger": {},
            "horizontal_position": None,
            "acquisition": {},
            "display": {},
            "errors": {},
        }
        window._apply_scope_snapshot(snapshot)
        assert window.bus_label.text() == "ECU"
        assert window.bus_type.currentText() == "I2C"

        window.bus_channel.setCurrentText("2")
        window._apply_cached_bus_configuration()
        assert window.bus_label.text() == "Vehicle CAN"
        assert window.bus_type.currentText() == "CAN"
        assert window.bus_state.isChecked() is False
        protocol_values = {
            window._bus_protocol_field_keys[row]: window.bus_protocol_table.item(row, 1).text()
            for row in range(window.bus_protocol_table.rowCount())
        }
        assert protocol_values["bit_rate"] == "500000"
        assert protocol_values["source"] == "CH3"
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
