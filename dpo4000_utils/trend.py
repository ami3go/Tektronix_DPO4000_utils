"""A20 bounded measurement trend model and spike-preserving decimation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import time
from typing import Iterable, Mapping

DEFAULT_TREND_CAPACITY = 100_000
DEFAULT_RENDER_POINTS = 2_000
MAX_TREND_CAPACITY = 1_000_000
MAX_TREND_SERIES = 64


class TrendValidationError(ValueError):
    """Raised when a trend sample/model parameter is invalid."""


@dataclass(frozen=True)
class TrendSample:
    timestamp_s: float
    value: float


@dataclass(frozen=True)
class TrendSnapshot:
    name: str
    samples: tuple[TrendSample, ...]
    total_received: int
    dropped_by_capacity: int

    @property
    def count(self) -> int:
        return len(self.samples)

    @property
    def first_timestamp_s(self) -> float | None:
        return self.samples[0].timestamp_s if self.samples else None

    @property
    def last_timestamp_s(self) -> float | None:
        return self.samples[-1].timestamp_s if self.samples else None


class _Series:
    def __init__(self, name: str, capacity: int) -> None:
        self.name = name
        self.samples: deque[TrendSample] = deque(maxlen=capacity)
        self.total_received = 0
        self.dropped_by_capacity = 0

    def append(self, sample: TrendSample) -> None:
        if len(self.samples) == self.samples.maxlen:
            self.dropped_by_capacity += 1
        self.samples.append(sample)
        self.total_received += 1

    def snapshot(self) -> TrendSnapshot:
        return TrendSnapshot(
            name=self.name,
            samples=tuple(self.samples),
            total_received=self.total_received,
            dropped_by_capacity=self.dropped_by_capacity,
        )


def _finite_number(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TrendValidationError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise TrendValidationError(f"{field} must be a finite number")
    return result


def _positive_int(value: object, *, field: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TrendValidationError(f"{field} must be an integer")
    if not 1 <= value <= maximum:
        raise TrendValidationError(f"{field} must be in range 1..{maximum}")
    return value


def decimate_minmax(
    samples: Iterable[TrendSample],
    max_points: int = DEFAULT_RENDER_POINTS,
) -> tuple[TrendSample, ...]:
    """Reduce samples to at most ``max_points`` while preserving bucket extrema.

    The first and last sample are retained. Interior samples are partitioned into
    chronological buckets; each bucket contributes its minimum and maximum value
    in original time order. This keeps narrow spikes visible without allocating a
    full rendered point for every stored sample.
    """
    limit = _positive_int(max_points, field="max_points", maximum=MAX_TREND_CAPACITY)
    values = tuple(samples)
    count = len(values)
    if count <= limit:
        return values
    if limit == 1:
        return (values[-1],)
    if limit == 2:
        return (values[0], values[-1])

    interior = values[1:-1]
    bucket_count = max(1, (limit - 2) // 2)
    bucket_size = max(1, math.ceil(len(interior) / bucket_count))
    selected: list[TrendSample] = [values[0]]
    for start in range(0, len(interior), bucket_size):
        bucket = interior[start : start + bucket_size]
        if not bucket:
            continue
        min_index = min(range(len(bucket)), key=lambda index: bucket[index].value)
        max_index = max(range(len(bucket)), key=lambda index: bucket[index].value)
        if min_index == max_index:
            selected.append(bucket[min_index])
        elif min_index < max_index:
            selected.extend((bucket[min_index], bucket[max_index]))
        else:
            selected.extend((bucket[max_index], bucket[min_index]))
        if len(selected) >= limit - 1:
            break
    selected = selected[: limit - 1]
    selected.append(values[-1])
    return tuple(selected)


class MeasurementTrendModel:
    """Bounded-memory multi-series trend storage suitable for live plotting."""

    def __init__(self, capacity: int = DEFAULT_TREND_CAPACITY) -> None:
        self.capacity = _positive_int(
            capacity,
            field="capacity",
            maximum=MAX_TREND_CAPACITY,
        )
        self._series: dict[str, _Series] = {}

    @property
    def series_names(self) -> tuple[str, ...]:
        return tuple(self._series)

    @property
    def total_stored_samples(self) -> int:
        return sum(len(series.samples) for series in self._series.values())

    def clear(self, name: str | None = None) -> None:
        if name is None:
            self._series.clear()
            return
        self._series.pop(self._normalize_name(name), None)

    @staticmethod
    def _normalize_name(name: object) -> str:
        if not isinstance(name, str) or not name.strip():
            raise TrendValidationError("series name must be a non-empty string")
        return name.strip()

    def _get_or_create(self, name: str) -> _Series:
        existing = self._series.get(name)
        if existing is not None:
            return existing
        if len(self._series) >= MAX_TREND_SERIES:
            raise TrendValidationError(
                f"trend model cannot exceed {MAX_TREND_SERIES} series"
            )
        created = _Series(name, self.capacity)
        self._series[name] = created
        return created

    def append(
        self,
        name: str,
        value: float,
        *,
        timestamp_s: float | None = None,
    ) -> TrendSample:
        normalized = self._normalize_name(name)
        numeric_value = _finite_number(value, field="value")
        timestamp = time.time() if timestamp_s is None else _finite_number(
            timestamp_s,
            field="timestamp_s",
        )
        series = self._get_or_create(normalized)
        if series.samples and timestamp < series.samples[-1].timestamp_s:
            raise TrendValidationError("timestamps must be monotonic within a series")
        sample = TrendSample(timestamp, numeric_value)
        series.append(sample)
        return sample

    def append_many(
        self,
        values: Mapping[str, float],
        *,
        timestamp_s: float | None = None,
    ) -> tuple[TrendSample, ...]:
        if not isinstance(values, Mapping):
            raise TrendValidationError("values must be a mapping")
        timestamp = time.time() if timestamp_s is None else _finite_number(
            timestamp_s,
            field="timestamp_s",
        )
        validated: list[tuple[str, float]] = []
        for name, value in values.items():
            validated.append(
                (self._normalize_name(name), _finite_number(value, field=f"{name} value"))
            )
        # Validate the whole batch before mutating any series.
        for name, _value in validated:
            existing = self._series.get(name)
            if existing and existing.samples and timestamp < existing.samples[-1].timestamp_s:
                raise TrendValidationError("timestamps must be monotonic within a series")
        return tuple(self.append(name, value, timestamp_s=timestamp) for name, value in validated)

    def snapshot(
        self,
        name: str,
        *,
        max_points: int | None = None,
    ) -> TrendSnapshot:
        normalized = self._normalize_name(name)
        series = self._series.get(normalized)
        if series is None:
            return TrendSnapshot(normalized, (), 0, 0)
        snapshot = series.snapshot()
        if max_points is None or snapshot.count <= max_points:
            return snapshot
        return TrendSnapshot(
            name=snapshot.name,
            samples=decimate_minmax(snapshot.samples, max_points),
            total_received=snapshot.total_received,
            dropped_by_capacity=snapshot.dropped_by_capacity,
        )

    def snapshots(
        self,
        *,
        max_points: int | None = None,
    ) -> tuple[TrendSnapshot, ...]:
        return tuple(
            self.snapshot(name, max_points=max_points) for name in self.series_names
        )


__all__ = [
    "DEFAULT_RENDER_POINTS",
    "DEFAULT_TREND_CAPACITY",
    "MAX_TREND_CAPACITY",
    "MAX_TREND_SERIES",
    "MeasurementTrendModel",
    "TrendSample",
    "TrendSnapshot",
    "TrendValidationError",
    "decimate_minmax",
]
