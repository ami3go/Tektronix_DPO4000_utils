import pytest

from dpo4000_utils.control import (
    AcquisitionConfig,
    ChannelConfig,
    DisplayConfig,
    MathConfig,
    MeasurementConfig,
    build_acquisition_setup_commands,
    build_channel_config_commands,
    build_channel_config_queries,
    build_clear_display_message_commands,
    build_disable_measurement_command,
    build_display_settings_commands,
    build_edge_trigger_commands,
    build_horizontal_position_command,
    build_math_config_commands,
    build_math_config_queries,
    build_measurement_commands,
    build_measurement_setup_queries,
    build_measurement_value_query,
    build_record_length_command,
    build_record_length_query,
    normalize_average_count,
    normalize_record_length,
    quote_scpi_string,
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


def test_measurement_setup_queries():
    assert build_measurement_setup_queries(3) == {
        "state": "MEASUREMENT:MEAS3:STATE?",
        "type": "MEASUREMENT:MEAS3:TYPE?",
        "source1": "MEASUREMENT:MEAS3:SOURCE1?",
        "source2": "MEASUREMENT:MEAS3:SOURCE2?",
        "value": "MEASUREMENT:MEAS3:VALUE?",
    }


def test_channel_config_commands_match_desk_fields():
    assert build_channel_config_commands(
        ChannelConfig(
            channel=2,
            display=True,
            scale="0.5",
            position="1",
            offset="0.1",
            coupling="ac",
            bandwidth="20E6",
            invert=False,
            probe_gain="10",
        )
    ) == [
        "SELECT:CH2 ON",
        "CH2:SCALE 0.5",
        "CH2:POSITION 1",
        "CH2:OFFSET 0.1",
        "CH2:COUPLING AC",
        "CH2:BANDWIDTH 2e+07",
        "CH2:PROBE:GAIN 10",
        "CH2:INVERT OFF",
    ]


def test_channel_config_queries_match_gui_readback():
    assert build_channel_config_queries(1)["probe_gain"] == "CH1:PROBE:GAIN?"


def test_math_config_commands_quote_expression():
    assert build_math_config_commands(
        MathConfig(display=True, define='CH1+"CH2"', scale="1", position="0")
    ) == [
        "MATH:DEFINE \"CH1+'CH2'\"",
        "MATH:VERTICAL:SCALE 1",
        "MATH:VERTICAL:POSITION 0",
        "SELECT:MATH ON",
    ]
    assert build_math_config_queries()["define"] == "MATH:DEFINE?"


def test_horizontal_position_command():
    assert build_horizontal_position_command("12.5") == "HORIZONTAL:POSITION 12.5"


def test_acquisition_setup_commands_average_and_record_length():
    assert build_acquisition_setup_commands(
        AcquisitionConfig(mode="average", average_count="16", record_length="10k")
    ) == [
        "ACQUIRE:MODE AVERAGE",
        "ACQUIRE:NUMAVG 16",
        "HORIZONTAL:RECORDLENGTH 10000",
    ]


def test_acquisition_setup_skips_average_count_for_non_average_mode():
    assert build_acquisition_setup_commands(
        AcquisitionConfig(mode="sample", average_count="16", record_length="1M")
    ) == [
        "ACQUIRE:MODE SAMPLE",
        "HORIZONTAL:RECORDLENGTH 1000000",
    ]


def test_record_length_label_normalization():
    assert normalize_record_length("1k") == 1000
    assert normalize_record_length("10 K") == 10000
    assert normalize_record_length("1M") == 1000000
    assert normalize_record_length("1e6") == 1000000
    assert normalize_record_length(1000.0) == 1000


def test_record_length_validation_rejects_bad_values():
    with pytest.raises(ValueError, match="Record length cannot be empty"):
        normalize_record_length("")
    with pytest.raises(ValueError, match="greater than zero"):
        normalize_record_length(0)
    with pytest.raises(ValueError, match="must be an integer"):
        normalize_record_length("12.5")
    with pytest.raises(ValueError, match="must be a numeric value"):
        normalize_record_length("deep")


def test_record_length_command_and_query():
    assert build_record_length_command("10k") == "HORIZONTAL:RECORDLENGTH 10000"
    assert build_record_length_command(2500) == "HORIZONTAL:RECORDLENGTH 2500"
    assert build_record_length_query() == "HORIZONTAL:RECORDLENGTH?"


def test_record_length_label_for_common_and_custom_values():
    assert record_length_label("100000") == "100k"
    assert record_length_label(2500) == "2500"


def test_average_count_validation():
    assert normalize_average_count("16") == 16
    with pytest.raises(ValueError, match="greater than zero"):
        normalize_average_count("0")


def test_display_settings_commands_match_display_page():
    assert build_display_settings_commands(
        DisplayConfig(
            backlight="80",
            waveform="70",
            graticule="40",
            persistence="auto",
            message_text="Hello\nScope",
            message_state=True,
        )
    ) == [
        "DISPLAY:INTENSITY:BACKLIGHT 80",
        "DISPLAY:INTENSITY:WAVEFORM 70",
        "DISPLAY:INTENSITY:GRATICULE 40",
        "DISPLAY:PERSISTENCE AUTO",
        "MESSAGE:SHOW \"Hello Scope\"",
        "MESSAGE:STATE ON",
    ]


def test_clear_display_message_commands():
    assert build_clear_display_message_commands() == ["MESSAGE:CLEAR", "MESSAGE:STATE OFF"]


def test_quote_scpi_string_single_line_and_safe_quotes():
    assert quote_scpi_string('A "quoted"\nmessage') == '"A \'quoted\' message"'


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
