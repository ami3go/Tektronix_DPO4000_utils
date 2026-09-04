from __future__ import annotations

from pathlib import Path


def test_l10_threshold_failure_is_counted_once_and_retained() -> None:
    source = (
        Path(__file__).parents[1]
        / "dpo4000_utils"
        / "gui_qt"
        / "logger_recovery_window.py"
    ).read_text(encoding="utf-8")
    assert "count_failure=False" in source
    assert "retain_closed_segments=True" in source
