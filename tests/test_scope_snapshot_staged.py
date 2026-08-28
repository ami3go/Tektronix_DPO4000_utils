from __future__ import annotations

from dpo4000_utils.connection import ConnectionMixin
from dpo4000_utils.scope_snapshot import (
    DEFAULT_OPTIONAL_FEATURE_TIMEOUT_MS,
    merge_scope_snapshots,
    read_bus_scope_snapshot,
)


class FakeVisa:
    def __init__(self):
        self.timeout = 20_000
        self.queries: list[tuple[str, int]] = []
        self.responses: dict[str, str | BaseException] = {
            # Family probe and disabled BUS1 common state.
            "BUS:B1:TYPE?": ":BUS:B1:TYPE I2C",
            "BUS:B1:STATE?": ":BUS:B1:STATE 0",
            "BUS:B1:LABEL?": ':BUS:B1:LABEL "Dormant"',
            "BUS:B1:POSITION?": ":BUS:B1:POSITION 0",
            "BUS:B1:DISPLAY:FORMAT?": ":BUS:B1:DISPLAY:FORMAT HEXADECIMAL",
            "BUS:B1:DISPLAY:TYPE?": ":BUS:B1:DISPLAY:TYPE BUS",
            # Enabled BUS2. Its CAN decoder answers one protocol field, then
            # intentionally times out. The reader must stop that protocol loop.
            "BUS:B2:TYPE?": ":BUS:B2:TYPE CAN",
            "BUS:B2:STATE?": ":BUS:B2:STATE 1",
            "BUS:B2:LABEL?": ':BUS:B2:LABEL "Vehicle"',
            "BUS:B2:POSITION?": ":BUS:B2:POSITION -1",
            "BUS:B2:DISPLAY:FORMAT?": ":BUS:B2:DISPLAY:FORMAT HEXADECIMAL",
            "BUS:B2:DISPLAY:TYPE?": ":BUS:B2:DISPLAY:TYPE BOTH",
            "BUS:B2:CAN:BITRATE?": ":BUS:B2:CAN:BITRATE 500000",
            "BUS:B2:CAN:PROBE?": TimeoutError("CAN probe setting unavailable"),
        }

    def query(self, command: str) -> str:
        self.queries.append((command, self.timeout))
        response = self.responses.get(command)
        if isinstance(response, BaseException):
            raise response
        if response is None:
            raise AssertionError(f"Unexpected query: {command}")
        return response


class ScopeUnderTest(ConnectionMixin):
    def __init__(self):
        self.scope = FakeVisa()


def test_bus_auto_snapshot_reads_common_all_buses_but_protocol_only_when_enabled():
    scope = ScopeUnderTest()

    snapshot = read_bus_scope_snapshot(scope, buses=(1, 2))

    assert snapshot["buses"][1]["state"] == "0"
    assert snapshot["buses"][1]["type"] == "I2C"
    assert snapshot["buses"][1]["protocol"] == {}

    assert snapshot["buses"][2]["state"] == "1"
    assert snapshot["buses"][2]["type"] == "CAN"
    assert snapshot["buses"][2]["protocol"] == {"bit_rate": "500000"}
    assert snapshot["errors"]["bus.bus2.protocol.probe"] == "CAN probe setting unavailable"

    commands = [command for command, _timeout in scope.scope.queries]
    assert not any(command.startswith("BUS:B1:I2C:") for command in commands)
    assert "BUS:B2:CAN:BITRATE?" in commands
    assert "BUS:B2:CAN:PROBE?" in commands
    assert "BUS:B2:CAN:SAMPLEPOINT?" not in commands
    assert "BUS:B2:CAN:SOURCE?" not in commands

    optional_timeouts = {
        timeout for command, timeout in scope.scope.queries if command.startswith("BUS:")
    }
    assert optional_timeouts == {DEFAULT_OPTIONAL_FEATURE_TIMEOUT_MS}
    assert scope.scope.timeout == 20_000


def test_merge_scope_snapshots_preserves_core_state_while_optional_stages_arrive():
    core = {
        "labels": {1: "INPUT"},
        "channels": {1: {"scale": "1"}},
        "math": {"define": "CH1-CH2"},
        "horizontal_position": 12.5,
        "errors": {"display": "optional display field unavailable"},
    }
    refs = {
        "references": {1: {"display": "1", "label": "Golden"}},
        "errors": {},
    }
    buses = {
        "buses": {1: {"state": "0", "type": "I2C", "protocol": {}}},
        "errors": {"bus.bus2.type": "not configured"},
    }

    merged = merge_scope_snapshots(core, refs, buses)

    assert merged["labels"] == {1: "INPUT"}
    assert merged["math"]["define"] == "CH1-CH2"
    assert merged["horizontal_position"] == 12.5
    assert merged["references"][1]["label"] == "Golden"
    assert merged["buses"][1]["type"] == "I2C"
    assert merged["errors"] == {
        "display": "optional display field unavailable",
        "bus.bus2.type": "not configured",
    }
