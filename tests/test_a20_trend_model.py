from __future__ import annotations

import math

import pytest

from dpo4000_utils.trend import (
    MAX_TREND_SERIES,
    MeasurementTrendModel,
    TrendSample,
    TrendValidationError,
    decimate_minmax,
)


def test_capacity_is_bounded_and_drop_count_is_explicit() -> None:
    model = MeasurementTrendModel(capacity=3)
    for index in range(5):
        model.append("MEAS1", float(index), timestamp_s=float(index))
    snapshot = model.snapshot("MEAS1")
    assert [sample.value for sample in snapshot.samples] == [2.0, 3.0, 4.0]
    assert snapshot.total_received == 5
    assert snapshot.dropped_by_capacity == 2
    assert model.total_stored_samples == 3


def test_batch_validation_is_atomic() -> None:
    model = MeasurementTrendModel(capacity=10)
    model.append("MEAS1", 1.0, timestamp_s=1.0)
    with pytest.raises(TrendValidationError):
        model.append_many({"MEAS1": 2.0, "MEAS2": math.nan}, timestamp_s=2.0)
    assert [sample.value for sample in model.snapshot("MEAS1").samples] == [1.0]
    assert model.snapshot("MEAS2").samples == ()


def test_timestamps_must_be_monotonic_per_series() -> None:
    model = MeasurementTrendModel()
    model.append("MEAS1", 1.0, timestamp_s=10.0)
    with pytest.raises(TrendValidationError, match="monotonic"):
        model.append("MEAS1", 2.0, timestamp_s=9.0)


def test_minmax_decimation_preserves_first_last_and_spike() -> None:
    samples = tuple(TrendSample(float(i), 1000.0 if i == 51 else float(i % 7)) for i in range(100))
    reduced = decimate_minmax(samples, 20)
    assert len(reduced) <= 20
    assert reduced[0] == samples[0]
    assert reduced[-1] == samples[-1]
    assert any(sample.value == 1000.0 for sample in reduced)
    assert [sample.timestamp_s for sample in reduced] == sorted(
        sample.timestamp_s for sample in reduced
    )


def test_snapshot_decimation_does_not_mutate_storage() -> None:
    model = MeasurementTrendModel(capacity=1000)
    for index in range(1000):
        model.append("MEAS1", float(index), timestamp_s=float(index))
    reduced = model.snapshot("MEAS1", max_points=50)
    full = model.snapshot("MEAS1")
    assert reduced.count <= 50
    assert full.count == 1000
    assert full.total_received == reduced.total_received == 1000


def test_series_limit_is_bounded() -> None:
    model = MeasurementTrendModel(capacity=1)
    for index in range(MAX_TREND_SERIES):
        model.append(f"S{index}", float(index), timestamp_s=1.0)
    with pytest.raises(TrendValidationError, match="cannot exceed"):
        model.append("too-many", 1.0, timestamp_s=1.0)


@pytest.mark.parametrize("value", [None, True, "1", math.nan, math.inf, -math.inf])
def test_invalid_values_are_rejected(value) -> None:
    model = MeasurementTrendModel()
    with pytest.raises(TrendValidationError):
        model.append("MEAS1", value, timestamp_s=1.0)


def test_large_model_scaling_contract() -> None:
    model = MeasurementTrendModel(capacity=100_000)
    for index in range(100_000):
        model.append("MEAS1", float(index % 1000), timestamp_s=float(index))
    reduced = model.snapshot("MEAS1", max_points=2_000)
    assert model.total_stored_samples == 100_000
    assert reduced.count <= 2_000
    assert reduced.samples[0].timestamp_s == 0.0
    assert reduced.samples[-1].timestamp_s == 99_999.0
