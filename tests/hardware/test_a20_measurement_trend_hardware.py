"""Read-only A20 integration qualification against a real DPO4000 scope."""

from __future__ import annotations

import math
import os
from collections.abc import Iterator

import pytest

from dpo4000_utils import DPO4054
from dpo4000_utils.connection import visaResourceAddr
from dpo4000_utils.trend import MeasurementTrendModel

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


@pytest.fixture(scope="module")
def a20_scope() -> Iterator[DPO4054]:
    if not _env_enabled("DPO4000_HARDWARE"):
        pytest.skip("Set DPO4000_HARDWARE=1 to run A20 hardware qualification.")
    resource = os.getenv("DPO4000_RESOURCE", visaResourceAddr).strip()
    if not resource:
        pytest.skip("Set DPO4000_RESOURCE to the oscilloscope VISA resource.")
    scope = DPO4054(resource, auto_connect=False, timeout_ms=20_000)
    scope.connect()
    try:
        identity = scope.query_identity()
        expected = os.getenv("DPO4000_EXPECT_IDN", "TEKTRONIX,DPO4054").strip()
        assert expected.upper() in identity.upper()
        yield scope
    finally:
        scope.disconnect()


@pytest.mark.hardware
def test_a20_active_measurements_feed_bounded_model(a20_scope: DPO4054) -> None:
    setups = a20_scope.get_all_measurement_setups()
    values: dict[str, float] = {}
    for slot, setup in setups.items():
        if str(setup.state).upper() != "ON":
            continue
        try:
            value = float(str(setup.value).strip().split()[-1])
        except (ValueError, IndexError):
            continue
        if math.isfinite(value):
            values[f"MEAS{slot}"] = value
    if not values:
        pytest.skip("A20 read-only HIL requires at least one active finite MEAS1..MEAS8 value.")

    model = MeasurementTrendModel(capacity=100)
    model.append_many(values, timestamp_s=1.0)
    model.append_many(values, timestamp_s=2.0)
    assert model.series_names
    for name in values:
        snapshot = model.snapshot(name, max_points=10)
        assert snapshot.count == 2
        assert all(math.isfinite(sample.value) for sample in snapshot.samples)
