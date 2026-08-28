from __future__ import annotations

import pytest

from dpo4000_utils.bus import BUS_COUNT_QUERY, BusMixin
from dpo4000_utils.connection import ConnectionMixin
from dpo4000_utils.errors import DPOTransportError
from dpo4000_utils.reference import REFERENCE_COUNT_QUERY, ReferenceMixin


class FakeVisa:
    def __init__(self, responses):
        self.responses = dict(responses)
        self.timeout = 20_000
        self.queries: list[tuple[str, int]] = []

    def query(self, command: str) -> str:
        self.queries.append((command, self.timeout))
        response = self.responses.get(command)
        if isinstance(response, BaseException):
            raise response
        if response is None:
            raise AssertionError(f"Unexpected query {command}")
        return response


class BusDriver(BusMixin, ConnectionMixin):
    def __init__(self, visa: FakeVisa):
        self.scope = visa
        self.read_slots: list[int] = []

    def get_bus_configuration(self, bus):
        self.read_slots.append(int(bus))
        return {"slot": int(bus)}


class ReferenceDriver(ReferenceMixin, ConnectionMixin):
    def __init__(self, visa: FakeVisa):
        self.scope = visa
        self.read_slots: list[int] = []

    def get_reference_configuration(self, reference):
        self.read_slots.append(int(reference))
        return {"slot": int(reference)}


def test_bus_public_capability_api_limits_get_all_to_reported_slots():
    visa = FakeVisa({BUS_COUNT_QUERY: ":CONFIGURATION:BUSWAVEFORMS:NUMBUS 2"})
    driver = BusDriver(visa)

    assert driver.get_bus_waveform_count() == 2
    assert driver.get_available_bus_slots() == (1, 2)
    assert driver.get_all_bus_configurations() == {1: {"slot": 1}, 2: {"slot": 2}}
    assert driver.read_slots == [1, 2]
    assert not any(command.startswith("BUS:B3:") for command, _ in visa.queries)
    assert not any(command.startswith("BUS:B4:") for command, _ in visa.queries)
    assert visa.timeout == 20_000


def test_reference_public_capability_api_limits_get_all_to_reported_slots():
    visa = FakeVisa({REFERENCE_COUNT_QUERY: ":CONFIGURATION:REFS:NUMREFS 2"})
    driver = ReferenceDriver(visa)

    assert driver.get_reference_waveform_count() == 2
    assert driver.get_available_reference_slots() == (1, 2)
    assert driver.get_all_reference_configurations() == {1: {"slot": 1}, 2: {"slot": 2}}
    assert driver.read_slots == [1, 2]
    assert visa.timeout == 20_000


def test_bus_capability_fallback_stops_at_first_missing_contiguous_slot():
    visa = FakeVisa(
        {
            BUS_COUNT_QUERY: TimeoutError("count query unsupported"),
            "*IDN?": "TEKTRONIX,DPO4054,SN,1.0",
            "BUS:B1:TYPE?": ":BUS:B1:TYPE I2C",
            "BUS:B2:TYPE?": ":BUS:B2:TYPE CAN",
            "BUS:B3:TYPE?": TimeoutError("BUS3 unavailable"),
        }
    )
    driver = BusDriver(visa)

    assert driver.get_bus_waveform_count() == 2
    commands = [command for command, _ in visa.queries]
    assert "BUS:B4:TYPE?" not in commands
    assert visa.timeout == 20_000


def test_reference_capability_fallback_stops_at_first_missing_contiguous_slot():
    visa = FakeVisa(
        {
            REFERENCE_COUNT_QUERY: TimeoutError("count query unsupported"),
            "*IDN?": "TEKTRONIX,DPO4054,SN,1.0",
            "SELECT:REF1?": ":SELECT:REF1 0",
            "SELECT:REF2?": ":SELECT:REF2 0",
            "SELECT:REF3?": TimeoutError("REF3 unavailable"),
        }
    )
    driver = ReferenceDriver(visa)

    assert driver.get_reference_waveform_count() == 2
    commands = [command for command, _ in visa.queries]
    assert "SELECT:REF4?" not in commands
    assert visa.timeout == 20_000


def test_capability_timeout_is_not_swallowed_when_session_health_check_fails():
    visa = FakeVisa(
        {
            BUS_COUNT_QUERY: TimeoutError("count timeout"),
            "*IDN?": TimeoutError("device disconnected"),
        }
    )
    driver = BusDriver(visa)

    with pytest.raises(DPOTransportError, match="session health check"):
        driver.get_bus_waveform_count()
