"""Framework-neutral A8 run count and elapsed-duration limits."""

from __future__ import annotations

import math
from dataclasses import dataclass

MAX_RUN_EVENTS = 1_000_000_000
MAX_RUN_DURATION_S = 365.0 * 24.0 * 60.0 * 60.0


@dataclass(frozen=True)
class RunLimits:
    """Optional successful-event and elapsed wall-clock limits."""

    max_events: int | None = None
    max_duration_s: float | None = None

    def __post_init__(self) -> None:
        events = self.max_events
        if events is not None:
            if isinstance(events, bool):
                raise ValueError("Maximum event count must be a positive integer.")
            try:
                numeric = float(events)
                normalized = int(events)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Maximum event count must be a positive integer.") from exc
            if not math.isfinite(numeric) or numeric != float(normalized) or normalized < 1:
                raise ValueError("Maximum event count must be a positive integer.")
            if normalized > MAX_RUN_EVENTS:
                raise ValueError(f"Maximum event count must not exceed {MAX_RUN_EVENTS:,}.")
            object.__setattr__(self, "max_events", normalized)

        duration = self.max_duration_s
        if duration is not None:
            value = float(duration)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError("Maximum run duration must be greater than zero.")
            if value > MAX_RUN_DURATION_S:
                raise ValueError("Maximum run duration must not exceed 365 days.")
            object.__setattr__(self, "max_duration_s", value)

    @property
    def enabled(self) -> bool:
        return self.max_events is not None or self.max_duration_s is not None


@dataclass(frozen=True)
class RunLimitStatus:
    """Current A8 limit state."""

    reached: bool
    reason: str = ""
    successful_events: int = 0
    elapsed_s: float = 0.0
    remaining_events: int | None = None
    remaining_s: float | None = None


class RunLimitTracker:
    """Track one run and evaluate count/duration boundaries without Qt."""

    def __init__(self, limits: RunLimits) -> None:
        self.limits = limits
        self._started_s: float | None = None
        self._reason = ""

    @property
    def started(self) -> bool:
        return self._started_s is not None

    @property
    def stop_reason(self) -> str:
        return self._reason

    def start(self, now_s: float) -> None:
        now = float(now_s)
        if not math.isfinite(now):
            raise ValueError("Run start time must be finite.")
        self._started_s = now
        self._reason = ""

    def reset(self) -> None:
        self._started_s = None
        self._reason = ""

    def status(self, successful_events: int, now_s: float) -> RunLimitStatus:
        if isinstance(successful_events, bool):
            raise ValueError("Successful event count must be a non-negative integer.")
        successes = int(successful_events)
        if successes < 0 or float(successful_events) != float(successes):
            raise ValueError("Successful event count must be a non-negative integer.")
        now = float(now_s)
        if not math.isfinite(now):
            raise ValueError("Run-limit evaluation time must be finite.")
        elapsed = 0.0 if self._started_s is None else max(0.0, now - self._started_s)

        remaining_events = None
        if self.limits.max_events is not None:
            remaining_events = max(0, self.limits.max_events - successes)
        remaining_s = None
        if self.limits.max_duration_s is not None:
            remaining_s = max(0.0, self.limits.max_duration_s - elapsed)

        if not self._reason:
            if self.limits.max_events is not None and successes >= self.limits.max_events:
                self._reason = f"Maximum event count reached ({self.limits.max_events})"
            elif self.limits.max_duration_s is not None and elapsed >= self.limits.max_duration_s:
                self._reason = (
                    f"Maximum run duration reached ({self.limits.max_duration_s:g} s)"
                )

        return RunLimitStatus(
            reached=bool(self._reason),
            reason=self._reason,
            successful_events=successes,
            elapsed_s=elapsed,
            remaining_events=remaining_events,
            remaining_s=remaining_s,
        )


__all__ = [
    "MAX_RUN_DURATION_S",
    "MAX_RUN_EVENTS",
    "RunLimits",
    "RunLimitStatus",
    "RunLimitTracker",
]
