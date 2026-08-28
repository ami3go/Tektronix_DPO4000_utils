from __future__ import annotations

from dataclasses import dataclass

from dpo4000_utils.scope_snapshot import read_scope_snapshot
from dpo4000_utils.trigger import TriggerMixin


@dataclass
class FakeMeasurement:
    slot: int
    state: str = "ON"
    measurement_type: str = "FREQUENCY"
    source1: str = "CH1"
    source2: str = ""
    value: str = "1.0E3"


class FakeScope:
    def get_channel_label(self, channel: int):
        return f"INPUT{channel}"

    def get_channel_configuration(self, channel: int):
        return {"display": "ON", "scale": str(channel), "coupling": "DC"}

    def get_math_configuration(self):
        return {"display": "OFF", "define": "CH1-CH2", "scale": "1"}

    def get_all_measurement_setups(self):
        return {1: FakeMeasurement(1)}

    def get_edge_trigger_configuration(self):
        return {
            "mode": "AUTO",
            "source": "CH2",
            "slope": "RISE",
            "coupling": "DC",
            "level": "0.5",
        }

    def get_horizontal_position(self):
        return 12.5

    def get_acquisition_setup(self):
        return {"mode": "AVERAGE", "average_count": "16", "record_length": "10000"}

    def get_display_settings(self):
        return {"backlight": "80", "persistence": "AUTO", "message_state": "OFF"}


def test_scope_snapshot_reads_all_gui_sections_in_one_driver_object():
    snapshot = read_scope_snapshot(FakeScope(), channels=(1, 2))

    assert snapshot["labels"] == {1: "INPUT1", 2: "INPUT2"}
    assert snapshot["channels"][2]["scale"] == "2"
    assert snapshot["math"]["define"] == "CH1-CH2"
    assert snapshot["measurements"][1].measurement_type == "FREQUENCY"
    assert snapshot["trigger"]["source"] == "CH2"
    assert snapshot["horizontal_position"] == 12.5
    assert snapshot["acquisition"]["record_length"] == "10000"
    assert snapshot["display"]["backlight"] == "80"
    assert snapshot["errors"] == {}


def test_scope_snapshot_isolates_one_failed_section():
    class PartialScope(FakeScope):
        def get_math_configuration(self):
            raise RuntimeError("math unavailable")

    snapshot = read_scope_snapshot(PartialScope(), channels=(1,))

    assert snapshot["math"] == {}
    assert snapshot["errors"]["math"] == "math unavailable"
    assert snapshot["trigger"]["source"] == "CH2"
    assert snapshot["display"]["backlight"] == "80"


class FakeVisa:
    def __init__(self):
        self.queries: list[str] = []
        self.responses = {
            "TRIGGER:A:EDGE:SOURCE?": ":TRIGGER:A:EDGE:SOURCE CH3",
            "TRIGGER:A:MODE?": ":TRIGGER:A:MODE NORMAL",
            "TRIGGER:A:EDGE:SLOPE?": ":TRIGGER:A:EDGE:SLOPE FALL",
            "TRIGGER:A:EDGE:COUPLING?": ":TRIGGER:A:EDGE:COUPLING AC",
            "TRIGGER:A:LEVEL:CH3?": ":TRIGGER:A:LEVEL:CH3 0.75",
        }

    def query(self, command: str) -> str:
        self.queries.append(command)
        return self.responses[command]


class TriggerUnderTest(TriggerMixin):
    def __init__(self):
        self.visa = FakeVisa()

    def ensure_connected(self):
        return self.visa


def test_edge_trigger_readback_uses_actual_channel_source_for_level():
    driver = TriggerUnderTest()

    result = driver.get_edge_trigger_configuration()

    assert result == {
        "mode": "NORMAL",
        "source": "CH3",
        "slope": "FALL",
        "coupling": "AC",
        "level": "0.75",
    }
    assert driver.visa.queries[-1] == "TRIGGER:A:LEVEL:CH3?"
