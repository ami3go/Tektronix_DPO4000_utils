from __future__ import annotations

from pathlib import Path

import pytest

from dpo4000_utils.automation import RunLimits, RunLimitTracker


def test_a8_limits_validate_count_and_duration() -> None:
    assert RunLimits().enabled is False
    assert RunLimits(max_events=100).max_events == 100
    assert RunLimits(max_duration_s=7200).max_duration_s == 7200
    with pytest.raises(ValueError, match="positive integer"):
        RunLimits(max_events=1.5)
    with pytest.raises(ValueError, match="greater than zero"):
        RunLimits(max_duration_s=0)


def test_a8_event_limit_has_no_off_by_one() -> None:
    tracker = RunLimitTracker(RunLimits(max_events=3))
    tracker.start(10.0)
    assert tracker.status(2, 12.0).reached is False
    status = tracker.status(3, 13.0)
    assert status.reached is True
    assert status.remaining_events == 0
    assert "event count" in status.reason


def test_a8_duration_limit_reports_remaining_and_stops_at_boundary() -> None:
    tracker = RunLimitTracker(RunLimits(max_duration_s=5.0))
    tracker.start(100.0)
    before = tracker.status(0, 104.9)
    assert before.reached is False
    assert before.remaining_s == pytest.approx(0.1)
    reached = tracker.status(0, 105.0)
    assert reached.reached is True
    assert reached.remaining_s == 0.0
    assert "duration" in reached.reason


def test_a8_stop_reason_is_stable_after_boundary() -> None:
    tracker = RunLimitTracker(RunLimits(max_events=1, max_duration_s=2.0))
    tracker.start(0.0)
    first = tracker.status(1, 1.0)
    assert first.reached is True
    assert "event count" in first.reason
    later = tracker.status(1, 10.0)
    assert later.reason == first.reason


def test_a8_gui_checks_all_recurring_schedulers_and_has_no_raw_io() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "dpo4000_utils" / "gui_qt" / "automation_limits_window.py").read_text(
        encoding="utf-8"
    )
    for hook in (
        "def _automation_tick",
        "def _trigger_cycle",
        "def _trigger_bundle_cycle",
        "def _schedule_next_burst",
        "def _run_limit_watchdog_tick",
    ):
        assert hook in source
    assert "RunLimitTracker" in source
    assert ".query(" not in source
    assert ".write(" not in source
    assert "CURVE?" not in source
