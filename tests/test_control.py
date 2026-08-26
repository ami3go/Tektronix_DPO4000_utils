import pytest

from dpo4000_utils.control import (
    MeasurementConfig,
    build_disable_measurement_command,
    build_edge_trigger_commands,
    build_horizontal_position_command,
    build_measurement_commands,
    build_measurement_value_query,
    build_record_length_command,
    build_record_length_query,
    normalize_record_length,
    record_length_label,
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


def test_record_length_label_normalization():
    assert normalize_record_length("1k") == 1000
    assert normalize_record_length("10 K") == 10000
    assert normalize_record_length("1M") == 1000000
    assert normalize_record_length("1e6") == 1000000
    assert normalize_record_length(1000.0) == 1000


def test_record_length_validation_rejects_bad_values():
    with pytest.raises(ValueError, match="Record length cannot be empty"):
        normalize_record_length("")
    with pytest.raises(ValueError, match="positive integer"):
        normalize_record_length(0)
    with pytest.raises(ValueError, match="positive integer"):
        normalize_record_length("12.5")
    with pytest.raises(ValueError, match="point count or label"):
        normalize_record_length("deep")


def test_record_length_command_and_query():
    assert build_record_length_command("10k") == "HORIZONTAL:RECORDLENGTH 10000"
    assert build_record_length_command(2500) == "HORIZONTAL:RECORDLENGTH 2500"
    assert build_record_length_query() == "HORIZONTAL:RECORDLENGTH?"


def test_record_length_label_for_common_and_custom_values():
    assert record_length_label("100000") == "100k"
    assert record_length_label(2500) == "2500"


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
