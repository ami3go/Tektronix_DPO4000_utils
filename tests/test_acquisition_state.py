from __future__ import annotations

import pytest

from dpo4000_utils.acquisition_state import (
    ACQUISITION_STATE_QUERY,
    ACQUISITION_COUNT_QUERY,
    STOP_AFTER_QUERY,
    MAX_ACQUISITION_COUNT,
    normalize_acquisition_count,
    normalize_stop_after,
    BUSY_QUERY,
    TRIGGER_STATE_QUERY,
    AcquisitionStateMixin,
    normalize_acquisition_state,
    normalize_busy_state,
    normalize_trigger_state,
)


class FakeInstrument:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = dict(responses)
        self.queries: list[str] = []
        self.writes: list[str] = []

    def write(self, command: str) -> None:
        self.writes.append(command)

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


def test_normalize_busy_state() -> None:
    for value in ("1", "ON", "BUSY", ":BUSY 1"):
        assert normalize_busy_state(value) is True
    for value in ("0", "OFF", "IDLE", ":BUSY 0"):
        assert normalize_busy_state(value) is False
    with pytest.raises(ValueError):
        normalize_busy_state("MAYBE")


def test_normalize_trigger_state_documented_values() -> None:
    for state in ("ARMED", "AUTO", "READY", "SAVE", "TRIGGER"):
        assert normalize_trigger_state(f":TRIGGER:STATE {state}") == state
    with pytest.raises(ValueError):
        normalize_trigger_state("UNKNOWN")


def test_normalize_trigger_state_accepts_dpo4054_abbreviations() -> None:
    cases = {
        "ARM": "ARMED",
        ":TRIGGER:STATE ARM": "ARMED",
        "REA": "READY",
        ":TRIGGER:STATE REA": "READY",
        "SAV": "SAVE",
        ":TRIGGER:STATE SAV": "SAVE",
        "TRIG": "TRIGGER",
        ":TRIGGER:STATE TRIG": "TRIGGER",
    }
    for response, expected in cases.items():
        assert normalize_trigger_state(response) == expected


def test_driver_exposes_acquisition_busy_and_trigger_state_queries() -> None:
    instrument = FakeInstrument(
        {
            ACQUISITION_STATE_QUERY: ":ACQUIRE:STATE 0",
            BUSY_QUERY: ":BUSY 0",
            TRIGGER_STATE_QUERY: ":TRIGGER:STATE SAV",
        }
    )
    driver = StateDriver(instrument)

    assert driver.get_acquisition_state() is False
    assert driver.is_acquiring() is False
    assert driver.is_busy() is False
    assert driver.get_trigger_state() == "SAVE"
    assert instrument.queries == [
        ACQUISITION_STATE_QUERY,
        ACQUISITION_STATE_QUERY,
        BUSY_QUERY,
        TRIGGER_STATE_QUERY,
    ]


@pytest.mark.parametrize("value, expected", [
    ("0", 0), ("1", 1), (":ACQUIRE:NUMACQ 350", 350),
    (str(MAX_ACQUISITION_COUNT), MAX_ACQUISITION_COUNT),
])
def test_acquisition_count_strict_valid_readbacks(value, expected):
    assert normalize_acquisition_count(value) == expected


@pytest.mark.parametrize("value", [
    "-1", "1.0", "NaN", "", "MISSING", str(2**32), "2;*RST",
])
def test_acquisition_count_rejects_unverifiable_readback(value):
    with pytest.raises(ValueError):
        normalize_acquisition_count(value)


@pytest.mark.parametrize("value, expected", [
    ("SEQ", "SEQUENCE"), (":ACQUIRE:STOPAFTER SEQUENCE", "SEQUENCE"),
    ("RUNST", "RUNSTOP"), ("RUNSTOP", "RUNSTOP"),
])
def test_stopafter_strict_readback(value, expected):
    assert normalize_stop_after(value) == expected


@pytest.mark.parametrize("value", ["", "AUTO", "1", "SEQ;*RST"])
def test_stopafter_rejects_unknown_or_injected_value(value):
    with pytest.raises(ValueError):
        normalize_stop_after(value)


def test_driver_exposes_counter_and_stopafter_without_mutating_acquisition():
    instrument = FakeInstrument({
        ACQUISITION_COUNT_QUERY: ":ACQUIRE:NUMACQ 1",
        STOP_AFTER_QUERY: ":ACQUIRE:STOPAFTER RUNSTOP",
    })
    driver = StateDriver(instrument)
    assert driver.get_acquisition_count() == 1
    assert driver.get_stop_after() == "RUNSTOP"
    driver.set_stop_after("SEQUENCE")
    assert instrument.queries == [ACQUISITION_COUNT_QUERY, STOP_AFTER_QUERY]
    assert instrument.writes == ["ACQUIRE:STOPAFTER SEQUENCE"]


def test_failed_counter_query_is_not_silently_synthesized():
    driver = StateDriver(FakeInstrument({}))
    with pytest.raises(KeyError):
        driver.get_acquisition_count()
