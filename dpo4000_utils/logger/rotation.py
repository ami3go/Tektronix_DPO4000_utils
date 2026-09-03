"""Logger segment-rotation policy."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class RotationPolicy:
    """OR-combined rotation thresholds evaluated between complete records."""

    max_bytes: int | None = 1_000_000_000
    max_duration_s: float | None = 3600.0
    max_records: int | None = None
    daily_utc: bool = False

    def __post_init__(self) -> None:
        max_bytes = self.max_bytes
        if max_bytes is not None:
            if isinstance(max_bytes, bool) or int(max_bytes) < 1:
                raise ValueError("Rotation max_bytes must be a positive integer or None.")
            max_bytes = int(max_bytes)

        duration = self.max_duration_s
        if duration is not None:
            duration = float(duration)
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError("Rotation max_duration_s must be positive and finite or None.")

        max_records = self.max_records
        if max_records is not None:
            if isinstance(max_records, bool) or int(max_records) < 1:
                raise ValueError("Rotation max_records must be a positive integer or None.")
            max_records = int(max_records)

        if not isinstance(self.daily_utc, bool):
            raise ValueError("Rotation daily_utc must be boolean.")

        object.__setattr__(self, "max_bytes", max_bytes)
        object.__setattr__(self, "max_duration_s", duration)
        object.__setattr__(self, "max_records", max_records)

    @property
    def enabled(self) -> bool:
        return any(
            (
                self.max_bytes is not None,
                self.max_duration_s is not None,
                self.max_records is not None,
                self.daily_utc,
            )
        )

    def should_rotate(
        self,
        *,
        segment_bytes: int,
        estimated_next_bytes: int,
        segment_records: int,
        segment_started_utc: datetime,
        now_utc: datetime | None = None,
    ) -> str | None:
        """Return the first matching rotation reason, or None."""
        if segment_records <= 0:
            return None
        now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        started = segment_started_utc.astimezone(timezone.utc)

        if self.max_bytes is not None:
            projected = max(0, int(segment_bytes)) + max(0, int(estimated_next_bytes))
            if projected > self.max_bytes:
                return "size"
        if self.max_duration_s is not None:
            elapsed = max(0.0, (now - started).total_seconds())
            if elapsed >= self.max_duration_s:
                return "duration"
        if self.max_records is not None and segment_records >= self.max_records:
            return "record_count"
        if self.daily_utc and now.date() != started.date():
            return "daily_utc"
        return None


__all__ = ["RotationPolicy"]
