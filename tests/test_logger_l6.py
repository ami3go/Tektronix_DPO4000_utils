from __future__ import annotations

from dpo4000_utils.bus_decoded import BusDecodedEvent
from dpo4000_utils.instrument import DPO4054
from dpo4000_utils.logger.models import LoggerConfig, LoggerMode
from dpo4000_utils.logger.producer import BusDecodedEventsUnavailable, capture_logger_record


def test_stock_driver_capability_gates_decoded_bus_events() -> None:
    scope = DPO4054(auto_connect=False)
    assert scope.supports_decoded_bus_events() is False


def test_bus_producer_fails_closed_when_capability_is_unqualified() -> None:
    class Scope:
        def supports_decoded_bus_events(self): return False
        def read_decoded_bus_events(self, _bus): raise AssertionError("must not be called")
    config = LoggerConfig(mode=LoggerMode.BUS, waveform_sources=(), bus_slots=(1,))
    try:
        capture_logger_record(Scope(), config, 1)
    except BusDecodedEventsUnavailable:
        pass
    else:
        raise AssertionError("BUS producer did not fail closed")


def test_structured_bus_event_contract() -> None:
    event = BusDecodedEvent(1, "I2C", 1e-6, "DATA", {"address": "0x50", "data": "AA"}, "")
    assert event.to_dict()["protocol"] == "I2C"
