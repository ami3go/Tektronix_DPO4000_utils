from __future__ import annotations

import pytest

from dpo4000_utils.control import ControlMixin, TriggerConfig
from dpo4000_utils.trigger import TriggerMixin


class FakeInstrument:
    def __init__(self, responses: dict | None = None) -> None:
        self.writes: list[str] = []
        self.queries: list[str] = []
        self.responses = dict(responses or {})

    def write(self, command: str) -> None:
        self.writes.append(command)

    def query(self, command: str) -> str:
        self.queries.append(command)
        value = self.responses.get(command)
        if value is None:
            raise AssertionError(f"Unexpected query: {command}")
        return value() if callable(value) else value


class FakeScope(ControlMixin, TriggerMixin):
    """Mixin composition mirroring DPO4000Scope's public trigger surface."""

    def __init__(self, responses: dict | None = None) -> None:
        self.instrument = FakeInstrument(responses)

    def ensure_connected(self):
        return self.instrument


def test_configure_trigger_edge_writes_edge_commands():
    scope = FakeScope()
    scope.configure_trigger(
        TriggerConfig(trigger_type="EDGE", source="CH1", slope="RISE", coupling="DC", mode="AUTO", level="1.0")
    )
    assert scope.instrument.writes == [
        "TRIGGER:A:TYPE EDGE",
        "TRIGGER:A:EDGE:SOURCE CH1",
        "TRIGGER:A:EDGE:SLOPE RISE",
        "TRIGGER:A:EDGE:COUPLING DC",
        "TRIGGER:A:MODE AUTO",
        "TRIGGER:A:LEVEL:CH1 1",
    ]


def test_configure_trigger_pulse_width_writes_pulse_commands():
    scope = FakeScope()
    scope.configure_trigger(
        TriggerConfig(
            trigger_type="PULSE",
            pulse_class="WIDTH",
            source="CH2",
            pulse_polarity="NEGATIVE",
            pulse_when="WITHIN",
            pulse_low_limit="1e-6",
            pulse_high_limit="2e-6",
        )
    )
    assert scope.instrument.writes == [
        "TRIGGER:A:TYPE PULSE",
        "TRIGGER:A:PULSE:CLASS WIDTH",
        "TRIGGER:A:PULSE:SOURCE CH2",
        "TRIGGER:A:PULSE:WIDTH:POLARITY NEGATIVE",
        "TRIGGER:A:PULSE:WIDTH:WHEN WITHIN",
        "TRIGGER:A:PULSE:WIDTH:LOWLIMIT 1e-06",
        "TRIGGER:A:PULSE:WIDTH:HIGHLIMIT 2e-06",
    ]


def test_configure_trigger_rejects_injected_field_before_any_write():
    scope = FakeScope()
    with pytest.raises(ValueError):
        scope.configure_trigger(
            TriggerConfig(trigger_type="PULSE", pulse_class="WIDTH", pulse_low_limit="1e-6;*RST")
        )
    assert scope.instrument.writes == []


def test_get_trigger_configuration_edge_delegates_to_get_edge_trigger_configuration():
    scope = FakeScope(
        responses={
            "TRIGGER:A:TYPE?": "EDG",
            "TRIGGER:A:EDGE:SOURCE?": "CH1",
            "TRIGGER:A:MODE?": "AUTO",
            "TRIGGER:A:EDGE:SLOPE?": "RIS",
            "TRIGGER:A:EDGE:COUPLING?": "DC",
            "TRIGGER:A:LEVEL:CH1?": "1.0000",
        }
    )
    result = scope.get_trigger_configuration()
    assert result == {
        "trigger_type": "EDGE",
        "mode": "AUTO",
        "source": "CH1",
        "slope": "RIS",
        "coupling": "DC",
        "level": "1.0000",
    }


def test_get_trigger_configuration_pulse_width_reads_class_specific_fields():
    scope = FakeScope(
        responses={
            "TRIGGER:A:TYPE?": "PULS",
            "TRIGGER:A:PULSE:CLASS?": "WID",
            "TRIGGER:A:PULSE:SOURCE?": "CH1",
            "TRIGGER:A:PULSE:WIDTH:POLARITY?": "POS",
            "TRIGGER:A:PULSE:WIDTH:WHEN?": "LESS",
            "TRIGGER:A:PULSE:WIDTH:LOWLIMIT?": "8.0000E-9",
            "TRIGGER:A:PULSE:WIDTH:HIGHLIMIT?": "12.0000E-9",
        }
    )
    result = scope.get_trigger_configuration()
    assert result == {
        "trigger_type": "PULSE",
        "pulse_class": "WIDTH",
        "source": "CH1",
        "pulse_polarity": "POS",
        "pulse_when": "LESS",
        "pulse_low_limit": "8.0000E-9",
        "pulse_high_limit": "12.0000E-9",
    }


def test_get_trigger_configuration_pulse_timeout_reads_class_specific_fields():
    scope = FakeScope(
        responses={
            "TRIGGER:A:TYPE?": "PULS",
            "TRIGGER:A:PULSE:CLASS?": "TIMEO",
            "TRIGGER:A:PULSE:SOURCE?": "CH1",
            "TRIGGER:A:PULSE:TIMEOUT:POLARITY?": "STAYSH",
            "TRIGGER:A:PULSE:TIMEOUT:TIME?": "8.0000E-9",
        }
    )
    result = scope.get_trigger_configuration()
    assert result == {
        "trigger_type": "PULSE",
        "pulse_class": "TIMEOUT",
        "source": "CH1",
        "pulse_polarity": "STAYSH",
        "pulse_timeout_time": "8.0000E-9",
    }


def test_get_trigger_configuration_unsupported_type_returns_raw_readback_only():
    scope = FakeScope(responses={"TRIGGER:A:TYPE?": "VID"})
    assert scope.get_trigger_configuration() == {"trigger_type": "VID"}


def test_configure_trigger_logic_pattern_writes_logic_commands():
    scope = FakeScope()
    scope.configure_trigger(
        TriggerConfig(
            trigger_type="LOGIC",
            logic_class="LOGIC",
            logic_function="OR",
            logic_input_ch1="HIGH",
            logic_input_ch2="X",
            logic_clock_source="NONE",
            logic_clock_edge="RISE",
            logic_when="TRUE",
        )
    )
    assert scope.instrument.writes == [
        "TRIGGER:A:TYPE LOGIC",
        "TRIGGER:A:LOGIC:CLASS LOGIC",
        "TRIGGER:A:LOGIC:FUNCTION OR",
        "TRIGGER:A:LOGIC:INPUT:CH1 HIGH",
        "TRIGGER:A:LOGIC:INPUT:CH2 X",
        "TRIGGER:A:LOGIC:INPUT:CLOCK:SOURCE NONE",
        "TRIGGER:A:LOGIC:INPUT:CLOCK:EDGE RISE",
        "TRIGGER:A:LOGIC:PATTERN:WHEN TRUE",
    ]


def test_configure_trigger_logic_sethold_writes_sethold_commands():
    scope = FakeScope()
    scope.configure_trigger(
        TriggerConfig(
            trigger_type="LOGIC",
            logic_class="SETHOLD",
            logic_clock_source="CH1",
            logic_clock_edge="RISE",
            logic_setup_time="5e-9",
            logic_hold_time="5e-9",
        )
    )
    assert scope.instrument.writes == [
        "TRIGGER:A:TYPE LOGIC",
        "TRIGGER:A:LOGIC:CLASS SETHOLD",
        "TRIGGER:A:LOGIC:SETHOLD:CLOCK:SOURCE CH1",
        "TRIGGER:A:LOGIC:SETHOLD:CLOCK:EDGE RISE",
        "TRIGGER:A:LOGIC:SETHOLD:SETTIME 5e-09",
        "TRIGGER:A:LOGIC:SETHOLD:HOLDTIME 5e-09",
    ]


def test_configure_trigger_logic_rejects_injected_field_before_any_write():
    scope = FakeScope()
    with pytest.raises(ValueError):
        scope.configure_trigger(
            TriggerConfig(trigger_type="LOGIC", logic_class="LOGIC", logic_function="AND;*RST")
        )
    assert scope.instrument.writes == []


def test_get_trigger_configuration_logic_pattern_reads_class_specific_fields():
    scope = FakeScope(
        responses={
            "TRIGGER:A:TYPE?": "LOGI",
            "TRIGGER:A:LOGIC:CLASS?": "LOGI",
            "TRIGGER:A:LOGIC:FUNCTION?": "AND",
            "TRIGGER:A:LOGIC:INPUT:CH1?": "X",
            "TRIGGER:A:LOGIC:INPUT:CH2?": "X",
            "TRIGGER:A:LOGIC:INPUT:CH3?": "X",
            "TRIGGER:A:LOGIC:INPUT:CH4?": "X",
            "TRIGGER:A:LOGIC:INPUT:CLOCK:SOURCE?": "NON",
            "TRIGGER:A:LOGIC:INPUT:CLOCK:EDGE?": "RIS",
            "TRIGGER:A:LOGIC:PATTERN:WHEN?": "TRU",
        }
    )
    result = scope.get_trigger_configuration()
    assert result == {
        "trigger_type": "LOGIC",
        "logic_class": "LOGIC",
        "logic_function": "AND",
        "logic_input_ch1": "X",
        "logic_input_ch2": "X",
        "logic_input_ch3": "X",
        "logic_input_ch4": "X",
        "logic_clock_source": "NON",
        "logic_clock_edge": "RIS",
        "logic_when": "TRU",
    }


def test_get_trigger_configuration_logic_sethold_reads_class_specific_fields():
    scope = FakeScope(
        responses={
            "TRIGGER:A:TYPE?": "LOGI",
            "TRIGGER:A:LOGIC:CLASS?": "SETH",
            "TRIGGER:A:LOGIC:SETHOLD:CLOCK:SOURCE?": "CH1",
            "TRIGGER:A:LOGIC:SETHOLD:CLOCK:EDGE?": "RIS",
            "TRIGGER:A:LOGIC:SETHOLD:CLOCK:THRESHOLD?": "1.0000",
            "TRIGGER:A:LOGIC:SETHOLD:DATA:THRESHOLD?": "1.0000",
            "TRIGGER:A:LOGIC:SETHOLD:SETTIME?": "8.0000E-9",
            "TRIGGER:A:LOGIC:SETHOLD:HOLDTIME?": "8.0000E-9",
        }
    )
    result = scope.get_trigger_configuration()
    assert result == {
        "trigger_type": "LOGIC",
        "logic_class": "SETHOLD",
        "logic_clock_source": "CH1",
        "logic_clock_edge": "RIS",
        "logic_clock_threshold": "1.0000",
        "logic_data_threshold": "1.0000",
        "logic_setup_time": "8.0000E-9",
        "logic_hold_time": "8.0000E-9",
    }


@pytest.mark.parametrize("level", ["nan", "inf", "-inf"])
def test_set_trigger_level_rejects_non_finite_values(level):
    scope = FakeScope()
    with pytest.raises(ValueError, match="finite"):
        scope.set_trigger_level(level, channel=1, verify=False)
    assert scope.instrument.writes == []


@pytest.mark.parametrize("preset", ["TTL", "ECL", "ttl", "ecl"])
def test_set_trigger_level_accepts_ttl_ecl_presets(preset):
    scope = FakeScope()
    scope.set_trigger_level(preset, channel=None, verify=False)
    assert scope.instrument.writes == [f"TRIGGER:A:LEVEL {preset.upper()}"]


def test_set_trigger_level_rejects_injected_command_before_write():
    scope = FakeScope()
    with pytest.raises(ValueError):
        scope.set_trigger_level("1;*RST", channel=2, verify=False)
    assert scope.instrument.writes == []


def test_set_trigger_level_channel_scoped_write():
    scope = FakeScope()
    scope.set_trigger_level(2.5, channel=3, verify=False)
    assert scope.instrument.writes == ["TRIGGER:A:LEVEL:CH3 2.5"]
