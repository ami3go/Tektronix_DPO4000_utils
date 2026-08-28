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


def _app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([sys.executable, "parameter-refresh-runtime-test"])
    return app


def test_full_parameter_refresh_runs_core_reference_bus_stages_in_order(monkeypatch):
    app = _app()
    window = QtScopeWindow()
    calls: list[str] = []
    applied: list[dict] = []
    try:
        monkeypatch.setattr(window, "_ensure_scope_parameter_pages_built", lambda: None)
        monkeypatch.setattr(window, "_apply_scope_snapshot", lambda snapshot: applied.append(snapshot))

        stage_results = {
            CORE_PARAMETER_REFRESH_DESCRIPTION: {
                "labels": {1: "INPUT1"},
                "channels": {1: {"scale": "1"}},
                "math": {"define": "CH1-CH2"},
                "horizontal_position": 5.0,
                "errors": {},
            },
            REFERENCE_PARAMETER_REFRESH_DESCRIPTION: {
                "references": {1: {"display": "1", "label": "REF_A"}},
                "errors": {},
            },
            BUS_PARAMETER_REFRESH_DESCRIPTION: {
                "buses": {1: {"state": "0", "type": "I2C", "protocol": {}}},
                "errors": {},
            },
        }

        def fake_run_action(description, callback):
            calls.append(description)
            return stage_results[description]

        monkeypatch.setattr(window, "_run_action", fake_run_action)
        window.read_all_parameters_after_connection.setChecked(True)
        window.refresh_scope_parameters()

        assert calls == [
            CORE_PARAMETER_REFRESH_DESCRIPTION,
            REFERENCE_PARAMETER_REFRESH_DESCRIPTION,
            BUS_PARAMETER_REFRESH_DESCRIPTION,
        ]
        assert len(applied) == 3
        assert applied[0]["labels"] == {1: "INPUT1"}
        assert applied[0]["references"] == {}
        assert applied[1]["labels"] == {1: "INPUT1"}
        assert applied[1]["references"][1]["label"] == "REF_A"
        assert applied[2]["buses"][1]["type"] == "I2C"
        assert "scope parameters loaded" in window.statusBar().currentMessage()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_staged_parameter_refresh_continues_if_optional_bus_stage_fails(monkeypatch):
    app = _app()
    window = QtScopeWindow()
    calls: list[str] = []
    try:
        monkeypatch.setattr(window, "_ensure_scope_parameter_pages_built", lambda: None)
        monkeypatch.setattr(window, "_apply_scope_snapshot", lambda snapshot: None)

        def fake_run_action(description, callback):
            calls.append(description)
            if description == BUS_PARAMETER_REFRESH_DESCRIPTION:
                return None
            return {"errors": {}}

        monkeypatch.setattr(window, "_run_action", fake_run_action)
        window.refresh_scope_parameters()

        assert calls[-1] == BUS_PARAMETER_REFRESH_DESCRIPTION
        assert window._connection_ok is True
        assert "1 warning" in window.statusBar().currentMessage()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
