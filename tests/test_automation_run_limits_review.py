from __future__ import annotations

from pathlib import Path


def test_a8_review_window_cleans_up_watchdog_and_stays_behind_driver_boundary() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "dpo4000_utils" / "gui_qt" / "automation_limits_review_window.py"
    ).read_text(encoding="utf-8")
    assert "_finalize_limit_tracking_if_inactive" in source
    assert "limits.max_duration_s is None" in source
    assert "watchdog.stop()" in source
    assert "def _automation_burst_event" in source
    assert ".query(" not in source
    assert ".write(" not in source
