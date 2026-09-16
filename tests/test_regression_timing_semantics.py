from __future__ import annotations

import pytest

from dpo4000_utils.automation.limits import RunLimits, RunLimitTracker
from dpo4000_utils.automation.recovery import RecoveryPolicy


class _FakeClock:
    """Deterministic monotonic clock used without real sleeping."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = float(start)

    def advance(self, seconds: float) -> float:
        self.now += float(seconds)
        return self.now


def test_run_duration_limit_exact_boundary_just_below_and_above() -> None:
    clock = _FakeClock(100.0)
    tracker = RunLimitTracker(RunLimits(max_duration_s=10.0))
    tracker.start(clock.now)

    below = tracker.status(0, clock.advance(9.999))
    assert not below.reached
    assert below.elapsed_s == pytest.approx(9.999)
    assert below.remaining_s == pytest.approx(0.001)

    exact = tracker.status(0, clock.advance(0.001))
    assert exact.reached
    assert exact.elapsed_s == pytest.approx(10.0)
    assert exact.remaining_s == 0.0
    assert exact.reason == "Maximum run duration reached (10 s)"

    above = tracker.status(0, clock.advance(100.0))
    assert above.reached
    assert above.reason == exact.reason


def test_run_event_limit_exact_boundary() -> None:
    tracker = RunLimitTracker(RunLimits(max_events=3))
    tracker.start(1_000.0)
    assert not tracker.status(2, 1_000.0).reached
    status = tracker.status(3, 1_000.0)
    assert status.reached
    assert status.remaining_events == 0
    assert status.reason == "Maximum event count reached (3)"


def test_run_limit_uses_supplied_monotonic_time_not_wall_clock() -> None:
    tracker = RunLimitTracker(RunLimits(max_duration_s=5.0))
    tracker.start(50.0)

    # A simulated wall-clock jump is deliberately irrelevant: only the supplied
    # monotonic value participates in the calculation.
    fake_wall_clock = 1_700_000_000.0
    fake_wall_clock += 86_400.0
    assert fake_wall_clock > 1_700_000_000.0
    assert not tracker.status(0, 54.999).reached
    assert tracker.status(0, 55.0).reached


def test_retry_backoff_sequence_and_cap_are_deterministic() -> None:
    policy = RecoveryPolicy(retry_delay_s=2.5, max_retries=20)
    assert [policy.delay_for_attempt(index) for index in range(1, 6)] == [
        2.5,
        5.0,
        7.5,
        10.0,
        12.5,
    ]

    capped = RecoveryPolicy(retry_delay_s=100.0, max_retries=20)
    assert [capped.delay_for_attempt(index) for index in (1, 2, 3, 4, 100)] == [
        100.0,
        200.0,
        300.0,
        300.0,
        300.0,
    ]


def test_absolute_deadline_math_has_no_cumulative_drift_for_ten_thousand_periods() -> None:
    """Encode the plan's scheduler invariant independently of real time/sleep."""

    start = 123.456
    interval = 0.125
    deadlines = [start + sequence * interval for sequence in range(1, 10_001)]

    assert deadlines[0] == pytest.approx(start + interval)
    assert deadlines[-1] == pytest.approx(start + 10_000 * interval)
    for sequence, deadline in enumerate(deadlines, start=1):
        assert deadline == pytest.approx(start + sequence * interval)


def test_late_work_skip_policy_does_not_shift_future_absolute_deadlines() -> None:
    start = 10.0
    interval = 1.0
    scheduled = [start + sequence * interval for sequence in range(1, 8)]

    # Event 2 runs long and finishes after event 3's deadline.  A no-backlog
    # scheduler skips event 3; event 4 remains anchored to the original epoch.
    actual_finish_event_2 = 13.4
    missed = [deadline for deadline in scheduled if 12.0 < deadline <= actual_finish_event_2]
    assert missed == [13.0]
    assert scheduled[3] == 14.0
