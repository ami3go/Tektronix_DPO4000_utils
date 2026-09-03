from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dpo4000_utils.logger.rotation import RotationPolicy


def test_rotation_policy_uses_first_matching_boundary() -> None:
    policy = RotationPolicy(
        max_bytes=1000,
        max_duration_s=60.0,
        max_records=10,
        daily_utc=True,
    )
    started = datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc)
    reason = policy.should_rotate(
        segment_bytes=900,
        estimated_next_bytes=200,
        segment_records=9,
        segment_started_utc=started,
        now_utc=started + timedelta(seconds=120),
    )
    assert reason == "size"


def test_rotation_never_creates_empty_segment() -> None:
    policy = RotationPolicy(max_bytes=1, max_duration_s=None)
    started = datetime.now(timezone.utc)
    assert (
        policy.should_rotate(
            segment_bytes=10,
            estimated_next_bytes=10,
            segment_records=0,
            segment_started_utc=started,
            now_utc=started,
        )
        is None
    )


def test_invalid_rotation_thresholds_fail_closed() -> None:
    with pytest.raises(ValueError):
        RotationPolicy(max_bytes=0)
    with pytest.raises(ValueError):
        RotationPolicy(max_duration_s=float("nan"))
    with pytest.raises(ValueError):
        RotationPolicy(max_records=0)
