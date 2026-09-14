from __future__ import annotations

import math
from typing import Any, Callable

import pytest

from dpo4000_utils.bus import BusConfig, BusMixin
from dpo4000_utils.control import ChannelConfig, ControlMixin, MeasurementConfig
from dpo4000_utils.reference import ReferenceConfig, ReferenceMixin


class _RecordingInstrument:
    def __init__(self) -> None:
        self.writes: list[str] = []
        self.queries: list[str] = []

    def write(self, command: str) -> None:
        self.writes.append(command)

    def query(self, command: str) -> str:
        self.queries.append(command)
        return ""


class _Driver(ControlMixin, BusMixin, ReferenceMixin):
    def __init__(self) -> None:
        self.instrument = _RecordingInstrument()

    def ensure_connected(self) -> _RecordingInstrument:
        return self.instrument


INDEX_REJECTS = (
    -100,
    -1,
    0,
    5,
    6,
    999,
    None,
    "",
    [],
    float("nan"),
    float("inf"),
    float("-inf"),
    "1;*RST",
    "1\n*RST",
    "1\r*RST",
)

MEASUREMENT_INDEX_REJECTS = (
    -100,
    -1,
    0,
    9,
    10,
    999,
    None,
    "",
    [],
    float("nan"),
    float("inf"),
    float("-inf"),
    "1;*RST",
    "1\n*RST",
    "1\r*RST",
)


def _assert_rejected_before_io(action: Callable[[_Driver], Any]) -> None:
    driver = _Driver()
    with pytest.raises((TypeError, ValueError, OverflowError)):
        action(driver)
    assert driver.instrument.writes == []
    assert driver.instrument.queries == []


@pytest.mark.parametrize("channel", INDEX_REJECTS)
def test_channel_boundary_matrix_rejects_before_visa_io(channel: Any) -> None:
    _assert_rejected_before_io(
        lambda driver: driver.configure_channel(ChannelConfig(channel=channel, display=True))
    )


@pytest.mark.parametrize("slot", MEASUREMENT_INDEX_REJECTS)
def test_measurement_slot_boundary_matrix_rejects_before_visa_io(slot: Any) -> None:
    _assert_rejected_before_io(
        lambda driver: driver.add_measurement(
            MeasurementConfig(slot=slot, measurement_type="FREQUENCY", source1="CH1")
        )
    )


@pytest.mark.parametrize("bus", INDEX_REJECTS)
def test_bus_boundary_matrix_rejects_before_visa_io(bus: Any) -> None:
    _assert_rejected_before_io(
        lambda driver: driver.configure_bus(BusConfig(bus=bus, state=True))
    )


@pytest.mark.parametrize("reference", INDEX_REJECTS)
def test_reference_boundary_matrix_rejects_before_visa_io(reference: Any) -> None:
    _assert_rejected_before_io(
        lambda driver: driver.configure_reference(ReferenceConfig(reference=reference, display=True))
    )


@pytest.mark.parametrize(
    "field,value",
    (
        ("source", "CH1;*RST"),
        ("source", "CH1\n*RST"),
        ("slope", "RISE;*RST"),
        ("coupling", "DC\r*RST"),
        ("mode", "AUTO;*RST"),
        ("level", "1.0;*RST"),
        ("level", float("nan")),
        ("level", float("inf")),
        ("level", float("-inf")),
    ),
)
def test_trigger_malformed_and_injection_values_generate_zero_io(field: str, value: Any) -> None:
    kwargs: dict[str, Any] = {
        "source": "CH1",
        "slope": "RISE",
        "coupling": "DC",
        "mode": "AUTO",
        "level": 1.25,
    }
    kwargs[field] = value
    _assert_rejected_before_io(lambda driver: driver.configure_edge_trigger(**kwargs))


def test_boundary_matrix_contains_non_finite_values() -> None:
    """Guard the plan requirement itself so NaN/+Inf/-Inf cannot disappear silently."""

    non_finite = [value for value in INDEX_REJECTS if isinstance(value, float) and not math.isfinite(value)]
    assert len(non_finite) == 3
