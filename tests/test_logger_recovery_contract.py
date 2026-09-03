from __future__ import annotations

from pathlib import Path

from dpo4000_utils.automation.recovery import RecoveryPolicy, RecoveryStatistics


def test_logger_reuses_bounded_recovery_policy() -> None:
    policy = RecoveryPolicy(
        enabled=True,
        max_retries=2,
        retry_delay_s=1.0,
        max_consecutive_failures=5,
    )
    assert policy.delay_for_attempt(1) == 1.0
    assert policy.delay_for_attempt(2) == 2.0


def test_consecutive_failure_streak_resets_after_reconnect() -> None:
    stats = RecoveryStatistics()
    stats.note_exhausted("first")
    stats.note_exhausted("second")
    assert stats.consecutive_failures == 2
    stats.note_reconnect_success()
    assert stats.consecutive_failures == 0


def test_logger_recovery_gui_contains_no_direct_visa_or_scpi_path() -> None:
    source = (
        Path(__file__).parents[1]
        / "dpo4000_utils"
        / "gui_qt"
        / "logger_recovery_window.py"
    ).read_text(encoding="utf-8").lower()
    assert "pyvisa" not in source
    assert "resource_manager" not in source
    assert "curve?" not in source
    assert "acquire:" not in source
