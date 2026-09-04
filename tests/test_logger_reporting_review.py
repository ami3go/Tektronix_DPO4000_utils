from __future__ import annotations

from pathlib import Path


def test_l14_review_layer_keeps_final_json_independent_from_run_end_event() -> None:
    source = Path("dpo4000_utils/gui_qt/logger_report_review_window.py").read_text(
        encoding="utf-8"
    )
    assert "reporter.append_event(" in source
    assert "reporter.finalize(" in source
    assert "except Exception" in source
    assert "fail_logger_on_error=False" in source


def test_l14_review_layer_preserves_driver_boundary() -> None:
    source = Path("dpo4000_utils/gui_qt/logger_report_review_window.py").read_text(
        encoding="utf-8"
    )
    lowered = source.lower()
    assert "pyvisa" not in lowered
    assert "curve?" not in lowered
    assert ".write(" not in source
    assert ".query(" not in source
