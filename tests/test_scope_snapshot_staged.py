from __future__ import annotations

from dpo4000_utils.connection import ConnectionMixin
from dpo4000_utils.scope_snapshot import (
    BUS_COUNT_QUERY,
    DEFAULT_OPTIONAL_FEATURE_TIMEOUT_MS,
    REFERENCE_COUNT_QUERY,
    merge_scope_snapshots,
    read_bus_scope_snapshot,
    read_reference_scope_snapshot,
)


class FakeVisa:
    def __init__(self):
        self.timeout = 20_000
        self.queries: list[tuple[str, int]] = []
        self.responses: dict[str, str | BaseException] = {
            BUS_COUNT_QUERY: ":CONFIGURATION:BUSWAVEFORMS:NUMBUS 2",
            # Disabled BUS1 common state.
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

    assert snapshot["capabilities"]["bus_count"] == 2
    assert snapshot["buses"][1]["state"] == "0"
    assert snapshot["buses"][1]["type"] == "I2C"
    assert snapshot["buses"][1]["protocol"] == {}

    assert snapshot["buses"][2]["state"] == "1"
    assert snapshot["buses"][2]["type"] == "CAN"
    assert snapshot["buses"][2]["protocol"] == {"bit_rate": "500000"}
    assert snapshot["errors"]["bus.bus2.protocol.probe"] == "CAN probe setting unavailable"

    commands = [command for command, _timeout in scope.scope.queries]
    assert commands[0] == BUS_COUNT_QUERY
    assert not any(command.startswith("BUS:B1:I2C:") for command in commands)
    assert "BUS:B2:CAN:BITRATE?" in commands
    assert "BUS:B2:CAN:PROBE?" in commands
    assert "BUS:B2:CAN:SAMPLEPOINT?" not in commands
    assert "BUS:B2:CAN:SOURCE?" not in commands

    optional_timeouts = {timeout for _command, timeout in scope.scope.queries}
    assert optional_timeouts == {DEFAULT_OPTIONAL_FEATURE_TIMEOUT_MS}
    assert scope.scope.timeout == 20_000


def test_bus_count_prevents_queries_for_nonexistent_bus3_and_bus4():
    scope = ScopeUnderTest()

    snapshot = read_bus_scope_snapshot(scope, buses=(1, 2, 3, 4))

    commands = [command for command, _timeout in scope.scope.queries]
    assert snapshot["capabilities"]["bus_count"] == 2
    assert set(snapshot["buses"]) == {1, 2}
    assert not any(command.startswith("BUS:B3:") for command in commands)
    assert not any(command.startswith("BUS:B4:") for command in commands)
    assert not any(key.startswith("bus.bus3") for key in snapshot["errors"])
    assert not any(key.startswith("bus.bus4") for key in snapshot["errors"])


class FakeReferenceVisa:
    def __init__(self):
        self.timeout = 20_000
        self.queries: list[str] = []
        self.responses = {
            REFERENCE_COUNT_QUERY: ":CONFIGURATION:REFS:NUMREFS 2",
            "SELECT:REF1?": ":SELECT:REF1 0",
            "REF1:LABEL?": ':REF1:LABEL "A"',
            "REF1:VERTICAL:SCALE?": ":REF1:VERTICAL:SCALE 1",
            "REF1:VERTICAL:POSITION?": ":REF1:VERTICAL:POSITION 0",
            "REF1:HORIZONTAL:SCALE?": ":REF1:HORIZONTAL:SCALE 1E-3",
            "REF1:HORIZONTAL:DELAY:TIME?": ":REF1:HORIZONTAL:DELAY:TIME 0",
            "REF1:DATE?": ':REF1:DATE ""',
            "REF1:TIME?": ':REF1:TIME ""',
            "SELECT:REF2?": ":SELECT:REF2 0",
            "REF2:LABEL?": ':REF2:LABEL "B"',
            "REF2:VERTICAL:SCALE?": ":REF2:VERTICAL:SCALE 1",
            "REF2:VERTICAL:POSITION?": ":REF2:VERTICAL:POSITION 0",
            "REF2:HORIZONTAL:SCALE?": ":REF2:HORIZONTAL:SCALE 1E-3",
            "REF2:HORIZONTAL:DELAY:TIME?": ":REF2:HORIZONTAL:DELAY:TIME 0",
            "REF2:DATE?": ':REF2:DATE ""',
            "REF2:TIME?": ':REF2:TIME ""',
        }

    def query(self, command: str) -> str:
        self.queries.append(command)
        return self.responses[command]


class ReferenceScopeUnderTest(ConnectionMixin):
    def __init__(self):
        self.scope = FakeReferenceVisa()


def test_reference_count_prevents_queries_beyond_reported_slots():
    scope = ReferenceScopeUnderTest()

    snapshot = read_reference_scope_snapshot(scope, references=(1, 2, 3, 4))

    assert snapshot["capabilities"]["reference_count"] == 2
    assert set(snapshot["references"]) == {1, 2}
    assert scope.scope.queries[0] == REFERENCE_COUNT_QUERY
    assert not any("REF3" in command or "REF4" in command for command in scope.scope.queries)
    assert snapshot["errors"] == {}
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
        "capabilities": {"reference_count": 4},
        "errors": {},
    }
    buses = {
        "buses": {1: {"state": "0", "type": "I2C", "protocol": {}}},
        "capabilities": {"bus_count": 2},
        "errors": {"bus.bus2.type": "not configured"},
    }

    merged = merge_scope_snapshots(core, refs, buses)

    assert merged["labels"] == {1: "INPUT"}
    assert merged["math"]["define"] == "CH1-CH2"
    assert merged["horizontal_position"] == 12.5
    assert merged["references"][1]["label"] == "Golden"
    assert merged["buses"][1]["type"] == "I2C"
    assert merged["capabilities"] == {"reference_count": 4, "bus_count": 2}
    assert merged["errors"] == {
        "display": "optional display field unavailable",
        "bus.bus2.type": "not configured",
    }
