from __future__ import annotations

from pathlib import Path


def test_a11_review_scopes_recovery_statistics_to_automation_runs() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "dpo4000_utils" / "gui_qt" / "automation_recovery_review_window.py"
    ).read_text(encoding="utf-8")
    assert "_reset_recovery_run_statistics" in source
    assert "self._recovery_statistics = RecoveryStatistics()" in source
    assert "if not replay_safe" in source
    assert "before_failures" in source
    assert "consecutive_failures = before_failures" in source
    assert ".query(" not in source
    assert ".write(" not in source
