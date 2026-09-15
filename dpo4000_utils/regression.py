"""Framework-neutral helpers for functional/timing regression gates.

The authoritative R0-T numbers are intentionally stored outside this module and
must be reviewed explicitly.  These helpers only implement deterministic
statistics and the relative+absolute acceptance policy from the regression plan.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class TimingSummary:
    """Stable latency distribution stored by R0-T captures."""

    minimum: float
    p50: float
    p95: float
    p99: float
    maximum: float
    sample_count: int


@dataclass(frozen=True)
class PerformanceGate:
    """Relative + absolute p95 regression policy.

    A candidate fails only when it exceeds *both* limits, matching the policy in
    ``docs/regression-test-plan.md``.  Shared CI can therefore use a meaningful
    absolute tolerance while controlled runners can use tighter baselines.
    """

    relative_limit: float = 1.30
    absolute_tolerance: float = 0.0

    def __post_init__(self) -> None:
        relative = float(self.relative_limit)
        absolute = float(self.absolute_tolerance)
        if not math.isfinite(relative) or relative < 1.0:
            raise ValueError("Relative regression limit must be finite and at least 1.0.")
        if not math.isfinite(absolute) or absolute < 0.0:
            raise ValueError("Absolute regression tolerance must be finite and non-negative.")
        object.__setattr__(self, "relative_limit", relative)
        object.__setattr__(self, "absolute_tolerance", absolute)

    def failed(self, *, baseline: TimingSummary, candidate: TimingSummary) -> bool:
        relative_exceeded = candidate.p95 > baseline.p95 * self.relative_limit
        absolute_exceeded = candidate.p95 - baseline.p95 > self.absolute_tolerance
        return bool(relative_exceeded and absolute_exceeded)


def _normalized_samples(samples: Iterable[float]) -> list[float]:
    values = [float(value) for value in samples]
    if not values:
        raise ValueError("At least one timing sample is required.")
    if any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ValueError("Timing samples must be finite and non-negative.")
    values.sort()
    return values


def percentile(samples: Sequence[float], fraction: float) -> float:
    """Return a deterministic linearly-interpolated percentile for sorted/unsorted data."""

    values = _normalized_samples(samples)
    q = float(fraction)
    if not math.isfinite(q) or q < 0.0 or q > 1.0:
        raise ValueError("Percentile fraction must be between 0 and 1.")
    if len(values) == 1:
        return values[0]
    index = (len(values) - 1) * q
    lower = int(math.floor(index))
    upper = int(math.ceil(index))
    if lower == upper:
        return values[lower]
    weight = index - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def summarize_timings(samples: Iterable[float]) -> TimingSummary:
    """Summarize one timing distribution as required by the R0-T plan."""

    values = _normalized_samples(samples)
    return TimingSummary(
        minimum=values[0],
        p50=percentile(values, 0.50),
        p95=percentile(values, 0.95),
        p99=percentile(values, 0.99),
        maximum=values[-1],
        sample_count=len(values),
    )


def linear_slope(samples: Iterable[float]) -> float:
    """Return least-squares slope versus sample index for drift/queue trend checks."""

    values = [float(value) for value in samples]
    if len(values) < 2:
        return 0.0
    if any(not math.isfinite(value) for value in values):
        raise ValueError("Trend samples must be finite.")
    n = float(len(values))
    mean_x = (n - 1.0) / 2.0
    mean_y = sum(values) / n
    numerator = sum((index - mean_x) * (value - mean_y) for index, value in enumerate(values))
    denominator = sum((index - mean_x) ** 2 for index in range(len(values)))
    return 0.0 if denominator == 0.0 else numerator / denominator


__all__ = [
    "PerformanceGate",
    "TimingSummary",
    "linear_slope",
    "percentile",
    "summarize_timings",
]
