from __future__ import annotations

from pathlib import Path


def test_a12_review_defers_run_once_finalization_until_outer_handler_returns() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "dpo4000_utils" / "gui_qt" / "automation_report_review_window.py"
    ).read_text(encoding="utf-8")
    assert "_automation_report_run_once_dispatch" in source
    assert "if self._automation_report_run_once_dispatch" in source
    method = source.split("def run_automation_once", 1)[1]
    assert method.index("super().run_automation_once()") < method.rindex(
        'self._finalize_automation_report("run_once_complete")'
    )
    assert ".query(" not in source
    assert ".write(" not in source
