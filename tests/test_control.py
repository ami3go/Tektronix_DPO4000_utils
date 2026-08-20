import pytest

from dpo4000_utils.control import (
    MeasurementConfig,
    build_disable_measurement_command,
    build_edge_trigger_commands,
    build_horizontal_position_command,
    build_measurement_commands,
    build_measurement_value_query,
)


def test_build_measurement_commands_single_source():
    assert build_measurement_commands(
        MeasurementConfig(slot=1, measurement_type="frequency", source1="ch1")
    ) == [
        "MEASUREMENT:MEAS1:TYPE FREQUENCY",
        "MEASUREMENT:MEAS1:SOURCE1 CH1",
        "MEASUREMENT:MEAS1:STATE ON",
    ]


def test_build_measurement_commands_two_sources():
    assert build_measurement_commands(
        MeasurementConfig(slot=2, measurement_type="delay", source1="CH1", source2="CH2")
    ) == [
        "MEASUREMENT:MEAS2:TYPE DELAY",
        "MEASUREMENT:MEAS2:SOURCE1 CH1",
        "MEASUREMENT:MEAS2:SOURCE2 CH2",
        "MEASUREMENT:MEAS2:STATE ON",
    ]


def test_measurement_slot_validation():
    with pytest.raises(ValueError, match="between 1 and 8"):
        build_disable_measurement_command(9)


def test_measurement_value_query():
    assert build_measurement_value_query(4) == "MEASUREMENT:MEAS4:VALUE?"


def test_horizontal_position_command():
    assert build_horizontal_position_command("12.5") == "HORIZONTAL:POSITION 12.5"


def test_edge_trigger_commands_channel_source():
    assert build_edge_trigger_commands(
        source="ch1",
        slope="rise",
        coupling="dc",
        mode="auto",
        level="1.25",
    ) == [
        "TRIGGER:A:TYPE EDGE",
        "TRIGGER:A:EDGE:SOURCE CH1",
        "TRIGGER:A:EDGE:SLOPE RISE",
        "TRIGGER:A:EDGE:COUPLING DC",
        "TRIGGER:A:MODE AUTO",
        "TRIGGER:A:LEVEL:CH1 1.25",
    ]


def test_edge_trigger_commands_aux_source_uses_general_level():
    assert build_edge_trigger_commands(
        source="aux",
        slope="fall",
        coupling="ac",
        mode="normal",
        level="TTL",
    )[-1] == "TRIGGER:A:LEVEL TTL"
