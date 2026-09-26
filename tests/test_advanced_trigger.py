from __future__ import annotations

import pytest

from dpo4000_utils.advanced_trigger import (
    AdvancedTriggerMixin,
    build_trigger_holdoff_command,
    build_trigger_holdoff_query,
    normalize_probe_query,
)
from dpo4000_utils.connection import ConnectionMixin
from dpo4000_utils.control import ControlMixin, TriggerConfig
from dpo4000_utils.errors import DPOTimeoutError
from dpo4000_utils.trigger import TriggerMixin


class FakeInstrument:
    def __init__(self, responses: dict[str, object] | None = None, *, timeout: int = 20_000) -> None:
        self.responses = dict(responses or {})
        self.timeout = timeout
        self.writes: list[str] = []
        self.queries: list[str] = []
        self.query_timeouts: list[tuple[str, int]] = []

    def write(self, command: str) -> None:
        self.writes.append(command)

    def query(self, command: str) -> str:
        self.queries.append(command)
        self.query_timeouts.append((command, self.timeout))
        if command not in self.responses:
            raise AssertionError(f"Unexpected query: {command}")
        value = self.responses[command]
        if isinstance(value, BaseException):
            raise value
        if callable(value):
            value = value()
        return str(value)


class FakeScope(ConnectionMixin, AdvancedTriggerMixin, ControlMixin, TriggerMixin):
    def __init__(self, responses: dict[str, object] | None = None, *, timeout: int = 20_000) -> None:
        self.scope = FakeInstrument(responses, timeout=timeout)
        self.rm = None


def _edge_config() -> TriggerConfig:
    return TriggerConfig(
        trigger_type="EDGE",
        source="CH1",
        slope="RISE",
        coupling="DC",
        mode="AUTO",
        level="1.0",
    )


def test_trigger_holdoff_contract() -> None:
    assert build_trigger_holdoff_command("1e-6") == "TRIGGER:A:HOLDOFF:VALUE 1e-06"
    assert build_trigger_holdoff_query() == "TRIGGER:A:HOLDOFF:VALUE?"


@pytest.mark.parametrize("value", ["-1", "nan", "inf", "-inf", "1e-6;*RST"])
def test_trigger_holdoff_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        build_trigger_holdoff_command(value)


def test_configure_trigger_validates_holdoff_before_any_write() -> None:
    scope = FakeScope()
    with pytest.raises(ValueError):
        scope.configure_trigger(_edge_config(), holdoff="1e-6;*RST")
    assert scope.scope.writes == []


def test_configure_trigger_appends_verified_holdoff_command() -> None:
    scope = FakeScope()
    scope.configure_trigger(_edge_config(), holdoff="1e-6")
    assert scope.scope.writes == [
        "TRIGGER:A:TYPE EDGE",
        "TRIGGER:A:EDGE:SOURCE CH1",
        "TRIGGER:A:EDGE:SLOPE RISE",
        "TRIGGER:A:EDGE:COUPLING DC",
        "TRIGGER:A:MODE AUTO",
        "TRIGGER:A:LEVEL:CH1 1",
        "TRIGGER:A:HOLDOFF:VALUE 1e-06",
    ]


def test_set_and_get_trigger_holdoff_round_trip() -> None:
    scope = FakeScope({"TRIGGER:A:HOLDOFF:VALUE?": "2.5000E-6"})
    value = scope.set_trigger_holdoff("2.5e-6")
    assert scope.scope.writes == ["TRIGGER:A:HOLDOFF:VALUE 2.5e-06"]
    assert value == pytest.approx(2.5e-6)


def test_get_trigger_configuration_includes_holdoff() -> None:
    scope = FakeScope(
        {
            "TRIGGER:A:TYPE?": "EDG",
            "TRIGGER:A:EDGE:SOURCE?": "CH1",
            "TRIGGER:A:MODE?": "AUTO",
            "TRIGGER:A:EDGE:SLOPE?": "RIS",
            "TRIGGER:A:EDGE:COUPLING?": "DC",
            "TRIGGER:A:LEVEL:CH1?": "1.0000",
            "TRIGGER:A:HOLDOFF:VALUE?": "5.0000E-7",
        }
    )
    assert scope.get_trigger_configuration() == {
        "trigger_type": "EDGE",
        "mode": "AUTO",
        "source": "CH1",
        "slope": "RIS",
        "coupling": "DC",
        "level": "1.0000",
        "holdoff": pytest.approx(5e-7),
    }


@pytest.mark.parametrize(
    "query",
    ["TRIGGER:A:HOLDOFF:BY", "TRIGGER:A:HOLDOFF:BY?;*RST", "TRIGGER:A:HOLDOFF:BY? *RST"],
)
def test_probe_query_validation_rejects_non_single_queries_without_io(query: str) -> None:
    scope = FakeScope()
    with pytest.raises(ValueError):
        scope.probe_scpi_query(query)
    assert scope.scope.writes == []
    assert scope.scope.queries == []


def test_normalize_probe_query_accepts_one_argument_free_query() -> None:
    assert normalize_probe_query("trigger:a:holdoff:by?") == "TRIGGER:A:HOLDOFF:BY?"


def test_supported_capability_probe_uses_temporary_bounded_timeout_and_restores_it() -> None:
    scope = FakeScope(
        {
            "TRIGGER:A:HOLDOFF:VALUE?": "5.0E-7",
            "*ESR?": "0",
        },
        timeout=20_000,
    )
    result = scope.probe_scpi_query("TRIGGER:A:HOLDOFF:VALUE?", timeout_ms=250)
    assert result.supported is True
    assert result.timed_out is False
    assert result.esr == 0
    assert result.response == "5.0E-7"
    assert scope.scope.query_timeouts == [
        ("TRIGGER:A:HOLDOFF:VALUE?", 250),
        ("*ESR?", 250),
    ]
    assert scope.scope.timeout == 20_000


def test_capability_probe_never_expands_existing_shorter_timeout() -> None:
    scope = FakeScope(
        {
            "TRIGGER:A:HOLDOFF:VALUE?": "5.0E-7",
            "*ESR?": "0",
        },
        timeout=100,
    )
    scope.probe_scpi_query("TRIGGER:A:HOLDOFF:VALUE?", timeout_ms=500)
    assert scope.scope.query_timeouts == [
        ("TRIGGER:A:HOLDOFF:VALUE?", 100),
        ("*ESR?", 100),
    ]
    assert scope.scope.timeout == 100


def test_prompt_scpi_error_is_unsupported_and_status_is_cleared() -> None:
    scope = FakeScope(
        {
            "TRIGGER:A:UNKNOWN?": "",
            "*ESR?": "32",
        }
    )
    result = scope.probe_scpi_query("TRIGGER:A:UNKNOWN?", timeout_ms=200)
    assert result.supported is False
    assert result.timed_out is False
    assert result.esr == 32
    assert scope.scope.writes == ["*CLS", "*CLS"]


@pytest.mark.parametrize(
    "timeout_error",
    [TimeoutError("timed out"), DPOTimeoutError("probe timed out")],
)
def test_timed_out_probe_is_unsupported_recovers_and_restores_timeout(timeout_error: BaseException) -> None:
    scope = FakeScope(
        {
            "TRIGGER:B:EVENTS:MODE?": timeout_error,
            "*IDN?": "TEKTRONIX,DPO4054,0,v2.68",
        },
        timeout=20_000,
    )
    result = scope.probe_scpi_query("TRIGGER:B:EVENTS:MODE?", timeout_ms=300)
    assert result.supported is False
    assert result.timed_out is True
    assert result.recovered is True
    assert scope.scope.writes == ["*CLS", "*CLS"]
    assert scope.scope.queries == ["TRIGGER:B:EVENTS:MODE?", "*IDN?"]
    assert scope.scope.query_timeouts == [
        ("TRIGGER:B:EVENTS:MODE?", 300),
        ("*IDN?", 300),
    ]
    assert scope.scope.timeout == 20_000
