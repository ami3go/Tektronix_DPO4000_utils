from __future__ import annotations

import pytest

from dpo4000_utils.bus import (
    BUS_PROTOCOL_COMMANDS,
    BUS_TYPES,
    BusConfig,
    BusMixin,
    build_bus_config_commands,
    build_bus_config_queries,
    build_bus_protocol_queries,
    bus_protocol_fields,
    canonical_bus_type,
    normalize_bus,
)


def test_bus_common_queries_cover_all_channel_level_fields():
    assert build_bus_config_queries(2) == {
        "state": "BUS:B2:STATE?",
        "type": "BUS:B2:TYPE?",
        "label": "BUS:B2:LABEL?",
        "position": "BUS:B2:POSITION?",
        "display_format": "BUS:B2:DISPLAY:FORMAT?",
        "display_type": "BUS:B2:DISPLAY:TYPE?",
    }


def test_bus_protocol_map_covers_programmer_manual_families():
    assert set(BUS_PROTOCOL_COMMANDS) == set(BUS_TYPES)
    assert set(BUS_PROTOCOL_COMMANDS) == {
        "AUDIO",
        "CAN",
        "FLEXRAY",
        "I2C",
        "LIN",
        "PARALLEL",
        "RS232C",
        "SPI",
        "USB",
    }
    parallel = BUS_PROTOCOL_COMMANDS["PARALLEL"]
    assert all(f"bit{bit}_source" in parallel for bit in range(16))
    assert {"clock_edge", "clock_is_clocked", "clock_source", "width"} <= set(parallel)


def test_spi_protocol_queries_use_bus_number_and_nested_command_paths():
    queries = build_bus_protocol_queries(3, "SPI")
    assert queries["clock_source"] == "BUS:B3:SPI:CLOCK:SOURCE?"
    assert queries["miso_source"] == "BUS:B3:SPI:DATA:MISO:SOURCE?"
    assert queries["mosi_source"] == "BUS:B3:SPI:DATA:MOSI:SOURCE?"
    assert queries["ss_source"] == "BUS:B3:SPI:SS:SOURCE?"
    assert queries["data_size"] == "BUS:B3:SPI:DATA:SIZE?"


def test_i2c_config_commands_apply_protocol_before_common_display_state():
    commands = build_bus_config_commands(
        BusConfig(
            bus=2,
            state=True,
            bus_type="i2c",
            label='ECU "diag"',
            position="-2",
            display_format="hexadecimal",
            display_type="bus",
            protocol_settings={
                "address_rw_include": True,
                "clock_source": "CH1",
                "data_source": "CH2",
            },
        )
    )

    assert commands == [
        "BUS:B2:TYPE I2C",
        "BUS:B2:I2C:ADDRESS:RWINCLUDE ON",
        "BUS:B2:I2C:CLOCK:SOURCE CH1",
        "BUS:B2:I2C:DATA:SOURCE CH2",
        "BUS:B2:LABEL \"ECU 'diag'\"",
        "BUS:B2:POSITION -2",
        "BUS:B2:DISPLAY:FORMAT HEXADECIMAL",
        "BUS:B2:DISPLAY:TYPE BUS",
        "BUS:B2:STATE ON",
    ]


def test_bus_aliases_and_validation_are_stable_but_future_types_are_not_blocked():
    assert canonical_bus_type("par") == "PARALLEL"
    assert canonical_bus_type("aud") == "AUDIO"
    assert canonical_bus_type("rs232") == "RS232C"
    assert canonical_bus_type("vendor_future") == "VENDORFUTURE"
    assert bus_protocol_fields("vendor_future") == ()

    with pytest.raises(ValueError, match="between 1 and 4"):
        normalize_bus(5)
    with pytest.raises(ValueError, match="Unsupported SPI protocol setting"):
        build_bus_config_commands(
            BusConfig(bus=1, bus_type="SPI", protocol_settings={"not_a_field": "CH1"})
        )


class FakeVisa:
    def __init__(self):
        self.writes: list[str] = []
        self.responses = {
            "BUS:B1:STATE?": ":BUS:B1:STATE 1",
            "BUS:B1:TYPE?": ":BUS:B1:TYPE I2C",
            "BUS:B1:LABEL?": ':BUS:B1:LABEL "Power rail"',
            "BUS:B1:POSITION?": ":BUS:B1:POSITION -1",
            "BUS:B1:DISPLAY:FORMAT?": ":BUS:B1:DISPLAY:FORMAT HEXADECIMAL",
            "BUS:B1:DISPLAY:TYPE?": ":BUS:B1:DISPLAY:TYPE BUS",
            "BUS:B1:I2C:ADDRESS:RWINCLUDE?": ":BUS:B1:I2C:ADDRESS:RWINCLUDE 1",
            "BUS:B1:I2C:CLOCK:SOURCE?": ":BUS:B1:I2C:CLOCK:SOURCE CH1",
            "BUS:B1:I2C:DATA:SOURCE?": ":BUS:B1:I2C:DATA:SOURCE CH2",
        }

    def query(self, command: str) -> str:
        return self.responses[command]

    def write(self, command: str) -> None:
        self.writes.append(command)


class BusUnderTest(BusMixin):
    def __init__(self):
        self.visa = FakeVisa()

    def ensure_connected(self):
        return self.visa


def test_bus_mixin_reads_active_protocol_and_applies_high_level_config():
    driver = BusUnderTest()

    config = driver.get_bus_configuration(1)
    assert config == {
        "state": "1",
        "type": "I2C",
        "label": "Power rail",
        "position": "-1",
        "display_format": "HEXADECIMAL",
        "display_type": "BUS",
        "protocol": {
            "address_rw_include": "1",
            "clock_source": "CH1",
            "data_source": "CH2",
        },
    }

    driver.configure_bus(
        BusConfig(
            bus=1,
            state=False,
            bus_type="I2C",
            protocol_settings={"clock_source": "CH3"},
        )
    )
    assert driver.visa.writes == [
        "BUS:B1:TYPE I2C",
        "BUS:B1:I2C:CLOCK:SOURCE CH3",
        "BUS:B1:STATE OFF",
    ]
