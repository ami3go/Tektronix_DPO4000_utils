from __future__ import annotations

import pytest

from dpo4000_utils.acquisition_state import (
    ACQUISITION_STATE_QUERY,
    TRIGGER_STATE_QUERY,
    AcquisitionStateMixin,
    normalize_acquisition_state,
    normalize_trigger_state,
)


class FakeInstrument:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = dict(responses)
        self.queries: list[str] = []

    def query(self, command: str) -> str:
        self.queries.append(command)
        return self.responses[command]


class StateDriver(AcquisitionStateMixin):
    def __init__(self, instrument: FakeInstrument) -> None:
        self.instrument = instrument

    def ensure_connected(self) -> FakeInstrument:
        return self.instrument


def test_normalize_acquisition_state() -> None:
    for value in ("1", "ON", "RUN", ":ACQUIRE:STATE 1"):
        assert normalize_acquisition_state(value) is True
    for value in ("0", "OFF", "STOP", ":ACQUIRE:STATE 0"):
        assert normalize_acquisition_state(value) is False
    with pytest.raises(ValueError):
        normalize_acquisition_state("MAYBE")


def test_normalize_trigger_state_documented_values() -> None:
    for state in ("ARMED", "AUTO", "READY", "SAVE", "TRIGGER"):
        assert normalize_trigger_state(f":TRIGGER:STATE {state}") == state
    with pytest.raises(ValueError):
        normalize_trigger_state("UNKNOWN")


def test_driver_exposes_acquisition_and_trigger_state_queries() -> None:
    instrument = FakeInstrument(
        {
            ACQUISITION_STATE_QUERY: ":ACQUIRE:STATE 0",
            TRIGGER_STATE_QUERY: ":TRIGGER:STATE SAVE",
        }
    )
    driver = StateDriver(instrument)

    assert driver.get_acquisition_state() is False
    assert driver.is_acquiring() is False
    assert driver.get_trigger_state() == "SAVE"
    assert instrument.queries == [
        ACQUISITION_STATE_QUERY,
        ACQUISITION_STATE_QUERY,
        TRIGGER_STATE_QUERY,
    ]
