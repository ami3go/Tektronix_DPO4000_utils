from __future__ import annotations

import math

import pytest

from dpo4000_utils.bus import BusConfig, build_bus_config_commands, canonical_bus_type
from dpo4000_utils.channels import ChannelMixin
from dpo4000_utils.control import (
    ChannelConfig,
    DisplayConfig,
    MeasurementConfig,
    build_channel_config_commands,
    build_display_settings_commands,
    build_edge_trigger_commands,
    build_measurement_commands,
)
from dpo4000_utils.errors import DPOTransportError
from dpo4000_utils.io_policy import optional_query
from dpo4000_utils.reference import ReferenceConfig, build_reference_config_commands
from dpo4000_utils.trigger import TriggerMixin


@pytest.mark.parametrize("bad", ["1;*RST", "1\n*RST", "1\r*RST"])
def test_channel_numeric_fields_reject_scpi_message_separators(bad):
    with pytest.raises(ValueError, match="SCPI message separator"):
        build_channel_config_commands(ChannelConfig(channel=1, scale=bad))


@pytest.mark.parametrize("bad", ["nan", "inf", "-inf"])
def test_channel_numeric_fields_reject_nonfinite_values(bad):
    with pytest.raises(ValueError, match="finite"):
        build_channel_config_commands(ChannelConfig(channel=1, scale=bad))


def test_channel_enum_and_measurement_tokens_reject_injected_commands():
    with pytest.raises(ValueError):
        build_channel_config_commands(ChannelConfig(channel=1, coupling="DC;*RST"))
    with pytest.raises(ValueError):
        build_measurement_commands(
            MeasurementConfig(slot=1, measurement_type="MAXIMUM;*RST", source1="CH1")
        )


def test_display_numeric_and_trigger_level_reject_injected_commands():
    with pytest.raises(ValueError):
        build_display_settings_commands(DisplayConfig(waveform="80;*RST"))
    with pytest.raises(ValueError):
        build_edge_trigger_commands(
            source="CH1",
            slope="RISE",
            coupling="DC",
            mode="AUTO",
            level="1;*RST",
        )


def test_bus_type_position_display_and_protocol_values_are_single_message_only():
    with pytest.raises(ValueError):
        canonical_bus_type("I2C;*RST")
    with pytest.raises(ValueError):
        build_bus_config_commands(BusConfig(bus=1, position="0;*RST"))
    with pytest.raises(ValueError):
        build_bus_config_commands(BusConfig(bus=1, display_type="BUS;*RST"))
    with pytest.raises(ValueError):
        build_bus_config_commands(
            BusConfig(
                bus=1,
                bus_type="I2C",
                protocol_settings={"clock_source": "CH1;*RST"},
            )
        )


def test_reference_numeric_values_reject_injection_and_nonfinite_values():
    with pytest.raises(ValueError):
        build_reference_config_commands(ReferenceConfig(reference=1, vertical_scale="1;*RST"))
    with pytest.raises(ValueError, match="finite"):
        build_reference_config_commands(ReferenceConfig(reference=1, vertical_scale=math.inf))


class LabelVisa:
    def __init__(self):
        self.writes: list[str] = []

    def write(self, command: str) -> None:
        self.writes.append(command)


class ChannelDriver(ChannelMixin):
    def __init__(self):
        self.visa = LabelVisa()
        self.channel_labels = {}

    def ensure_connected(self):
        return self.visa


def test_channel_labels_are_quoted_data_not_raw_scpi():
    driver = ChannelDriver()
    driver.set_channel_label(1, 'rail";*RST\nnext')

    assert len(driver.visa.writes) == 1
    assert driver.visa.writes[0].startswith('CH1:LABEL "')
    assert "\n" not in driver.visa.writes[0]
    assert driver.visa.writes[0].endswith('"')


class TriggerVisa:
    def __init__(self):
        self.writes: list[str] = []

    def write(self, command: str) -> None:
        self.writes.append(command)


class TriggerDriver(TriggerMixin):
    def __init__(self):
        self.visa = TriggerVisa()

    def ensure_connected(self):
        return self.visa


def test_trigger_mixin_rejects_injected_level_before_write():
    driver = TriggerDriver()
    with pytest.raises(ValueError):
        driver.set_trigger_level("1;*RST", channel=1, verify=False)
    assert driver.visa.writes == []


class HealthVisa:
    def __init__(self, *, health_ok: bool):
        self.health_ok = health_ok
        self.queries: list[str] = []

    def query(self, command: str):
        self.queries.append(command)
        if command == "OPTIONAL?":
            raise TimeoutError("optional field unavailable")
        if command == "*IDN?" and self.health_ok:
            return "TEKTRONIX,DPO4054,SN,1.0"
        raise TimeoutError("session lost")


def test_optional_query_distinguishes_unsupported_field_from_lost_session():
    alive = HealthVisa(health_ok=True)
    assert optional_query(alive, "OPTIONAL?") == ""
    assert alive.queries == ["OPTIONAL?", "*IDN?"]

    lost = HealthVisa(health_ok=False)
    with pytest.raises(DPOTransportError):
        optional_query(lost, "OPTIONAL?")
