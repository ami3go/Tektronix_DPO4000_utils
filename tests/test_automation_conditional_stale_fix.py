from __future__ import annotations

from pathlib import Path


def test_a6_stale_completion_guard_consumes_second_stop_path() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "dpo4000_utils" / "gui_qt" / "automation_conditional_review_window.py"
    ).read_text(encoding="utf-8")

    assert "_discarded_conditional_completion = True" in source
    assert "self._automation_controller.state is AutomationState.IDLE" in source
    assert "self._discarded_conditional_completion = False" in source
