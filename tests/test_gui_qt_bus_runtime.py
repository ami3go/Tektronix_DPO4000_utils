from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from dpo4000_utils.gui_qt.bus_window import (  # noqa: E402
    BUS_PARAMETER_REFRESH_DESCRIPTION,
    CORE_PARAMETER_REFRESH_DESCRIPTION,
    REFERENCE_PARAMETER_REFRESH_DESCRIPTION,
    QtScopeWindow,
)
from dpo4000_utils.gui_qt.desktop_window import CONNECTION_TEST_DESCRIPTION  # noqa: E402


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
    actions: list[str] = []
    retains: list[bool] = []
    try:
        monkeypatch.setattr(window, "_ensure_scope_parameter_pages_built", lambda: None)
        monkeypatch.setattr(window, "_apply_scope_snapshot", lambda snapshot: None)

        def fake_run_action(
            description,
            callback,
            *,
            on_success=None,
            on_error=None,
            retain_session=False,
        ):
            actions.append(description)
            retains.append(bool(retain_session))
            if description == CONNECTION_TEST_DESCRIPTION:
                result = "TEKTRONIX,DPO4054,C000001,CF:91.1"
            else:
                result = {"errors": {}}
            if on_success is not None:
                on_success(result)

        monkeypatch.setattr(window, "_run_action", fake_run_action)

        window.read_all_parameters_after_connection.setChecked(False)
        window.test_connection()
        assert actions == [CONNECTION_TEST_DESCRIPTION]
        assert retains == [True]
        assert "parameter read skipped" in window.statusBar().currentMessage()

        actions.clear()
        retains.clear()
        window.read_all_parameters_after_connection.setChecked(True)
        window.test_connection()
        assert actions == [
            CONNECTION_TEST_DESCRIPTION,
            CORE_PARAMETER_REFRESH_DESCRIPTION,
            REFERENCE_PARAMETER_REFRESH_DESCRIPTION,
            BUS_PARAMETER_REFRESH_DESCRIPTION,
        ]
        # IDN/Core/REF deliberately retain one coherent connection; BUS is the
        # final stage and may honor a user's per-operation close preference.
        assert retains == [True, True, True, False]
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_final_desktop_channels_page_builds_manual_maximum_before_connection():
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


def test_final_desktop_applies_cached_bus_snapshot_and_scope_reported_count():
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
            "capabilities": {"bus_count": 2},
            "errors": {},
        }
        window._apply_scope_snapshot(snapshot)
        assert [window.bus_channel.itemText(i) for i in range(window.bus_channel.count())] == [
            "1",
            "2",
        ]
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


def test_programmatic_bus_snapshot_update_does_not_emit_bus_type_change_signal():
    app = _app()
    window = QtScopeWindow()
    emitted: list[str] = []
    try:
        window._ensure_control_page_built(1)
        window.bus_type.currentTextChanged.connect(emitted.append)

        window._apply_bus_configuration_to_widgets(
            {
                "state": "1",
                "type": "CAN",
                "label": "CAN",
                "position": "0",
                "display_format": "HEXADECIMAL",
                "display_type": "BUS",
                "protocol": {"bit_rate": "500000", "source": "CH1"},
            }
        )

        assert window.bus_type.currentText() == "CAN"
        assert emitted == []
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
