from __future__ import annotations

from pathlib import Path


def test_l14_gui_keeps_scope_commands_out_of_reporting_layer() -> None:
    source = Path("dpo4000_utils/gui_qt/logger_report_window.py").read_text(encoding="utf-8")
    lowered = source.lower()
    assert "pyvisa" not in lowered
    assert "curve?" not in lowered
    assert "trigger:state?" not in lowered
    assert "acquire:state?" not in lowered
    assert ".write(" not in source
    assert ".query(" not in source


def test_l14_finalization_explicitly_waits_for_writer_shutdown() -> None:
    source = Path("dpo4000_utils/gui_qt/logger_report_window.py").read_text(encoding="utf-8")
    assert "or self._logger_writer_active():" in source
    assert "if self._logger_writer_active():" in source
    assert "records_reconciled" in source
    assert "stop_waiting_for_writer" in source
