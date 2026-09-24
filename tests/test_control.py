import pytest

from dpo4000_utils.control import (
    AcquisitionConfig,
    ChannelConfig,
    DisplayConfig,
    MathConfig,
    MeasurementConfig,
    TRIGGER_LOGIC_CLASSES,
    TRIGGER_PULSE_CLASSES,
    TRIGGER_TYPES,
    TriggerConfig,
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
    build_trigger_config_commands,
    build_trigger_config_queries,
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


def test_trigger_types_are_the_live_verified_set():
    # Regression guard: TRIGGER_TYPES previously listed RUNT/TIMEOUT as top-level types
    # and omitted BUS. Both were wrong - see docs/a14-advanced-trigger-backlog.md.
    assert TRIGGER_TYPES == ("EDGE", "LOGIC", "PULSE", "VIDEO", "BUS")
    assert "RUNT" not in TRIGGER_TYPES
    assert "TIMEOUT" not in TRIGGER_TYPES


def test_trigger_pulse_classes_are_the_live_verified_set():
    assert TRIGGER_PULSE_CLASSES == ("WIDTH", "RUNT", "TIMEOUT", "TRANSITION")


def test_trigger_config_commands_edge_matches_build_edge_trigger_commands():
    config = TriggerConfig(
        trigger_type="EDGE", source="ch1", slope="rise", coupling="dc", mode="auto", level="1.25"
    )
    assert build_trigger_config_commands(config) == build_edge_trigger_commands(
        source="ch1", slope="rise", coupling="dc", mode="auto", level="1.25"
    )


def test_trigger_config_edge_requires_all_edge_fields():
    with pytest.raises(ValueError, match="requires"):
        build_trigger_config_commands(TriggerConfig(trigger_type="EDGE", source="CH1"))


def test_trigger_config_commands_pulse_width():
    config = TriggerConfig(
        trigger_type="pulse",
        pulse_class="width",
        source="ch1",
        pulse_polarity="positive",
        pulse_when="lessthan",
        pulse_low_limit="8e-9",
        pulse_high_limit="12e-9",
        mode="auto",
    )
    assert build_trigger_config_commands(config) == [
        "TRIGGER:A:TYPE PULSE",
        "TRIGGER:A:PULSE:CLASS WIDTH",
        "TRIGGER:A:PULSE:SOURCE CH1",
        "TRIGGER:A:PULSE:WIDTH:POLARITY POSITIVE",
        "TRIGGER:A:PULSE:WIDTH:WHEN LESSTHAN",
        "TRIGGER:A:PULSE:WIDTH:LOWLIMIT 8e-09",
        "TRIGGER:A:PULSE:WIDTH:HIGHLIMIT 1.2e-08",
        "TRIGGER:A:MODE AUTO",
    ]


def test_trigger_config_commands_pulse_runt():
    config = TriggerConfig(
        trigger_type="PULSE",
        pulse_class="RUNT",
        pulse_polarity="EITHER",
        pulse_when="OCCURS",
        pulse_threshold_high="9.0",
        pulse_threshold_low="1.0",
    )
    commands = build_trigger_config_commands(config)
    assert commands == [
        "TRIGGER:A:TYPE PULSE",
        "TRIGGER:A:PULSE:CLASS RUNT",
        "TRIGGER:A:PULSE:RUNT:POLARITY EITHER",
        "TRIGGER:A:PULSE:RUNT:WHEN OCCURS",
        "TRIGGER:A:PULSE:RUNT:THRESHOLD:HIGH 9",
        "TRIGGER:A:PULSE:RUNT:THRESHOLD:LOW 1",
    ]


def test_trigger_config_commands_pulse_timeout():
    config = TriggerConfig(
        trigger_type="PULSE",
        pulse_class="TIMEOUT",
        pulse_polarity="STAYSHIGH",
        pulse_timeout_time="8e-9",
    )
    assert build_trigger_config_commands(config) == [
        "TRIGGER:A:TYPE PULSE",
        "TRIGGER:A:PULSE:CLASS TIMEOUT",
        "TRIGGER:A:PULSE:TIMEOUT:POLARITY STAYSHIGH",
        "TRIGGER:A:PULSE:TIMEOUT:TIME 8e-09",
    ]


def test_trigger_config_rejects_unsupported_trigger_type():
    with pytest.raises(ValueError, match="not yet supported"):
        build_trigger_config_commands(TriggerConfig(trigger_type="VIDEO"))


def test_trigger_config_rejects_invalid_trigger_type_before_any_command():
    with pytest.raises(ValueError):
        build_trigger_config_commands(TriggerConfig(trigger_type="NOT_A_TYPE"))


def test_trigger_config_rejects_invalid_pulse_class():
    with pytest.raises(ValueError):
        build_trigger_config_commands(TriggerConfig(trigger_type="PULSE", pulse_class="BOGUS"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("pulse_polarity", "SIDEWAYS"),
        ("pulse_when", "SIDEWAYS"),
    ],
)
def test_trigger_config_rejects_invalid_width_enum_values(field, value):
    with pytest.raises(ValueError):
        build_trigger_config_commands(
            TriggerConfig(trigger_type="PULSE", pulse_class="WIDTH", **{field: value})
        )


def test_trigger_config_width_rejects_either_polarity():
    # WIDTH only accepts POSITIVE/NEGATIVE; EITHER is valid for RUNT/TIMEOUT but not WIDTH.
    with pytest.raises(ValueError):
        build_trigger_config_commands(
            TriggerConfig(trigger_type="PULSE", pulse_class="WIDTH", pulse_polarity="EITHER")
        )


def test_trigger_config_queries_pulse_width():
    assert build_trigger_config_queries("PULSE", "WIDTH") == {
        "source": "TRIGGER:A:PULSE:SOURCE?",
        "pulse_polarity": "TRIGGER:A:PULSE:WIDTH:POLARITY?",
        "pulse_when": "TRIGGER:A:PULSE:WIDTH:WHEN?",
        "pulse_low_limit": "TRIGGER:A:PULSE:WIDTH:LOWLIMIT?",
        "pulse_high_limit": "TRIGGER:A:PULSE:WIDTH:HIGHLIMIT?",
    }


def test_trigger_config_queries_rejects_unsupported_type():
    with pytest.raises(ValueError, match="not yet supported"):
        build_trigger_config_queries("VIDEO")


def test_trigger_logic_classes_are_the_live_verified_set():
    assert TRIGGER_LOGIC_CLASSES == ("LOGIC", "SETHOLD")


def test_trigger_config_commands_logic_pattern():
    config = TriggerConfig(
        trigger_type="logic",
        logic_class="logic",
        logic_function="and",
        logic_input_ch1="high",
        logic_input_ch2="low",
        logic_input_ch3="x",
        logic_input_ch4="x",
        logic_clock_source="none",
        logic_clock_edge="rise",
        logic_when="true",
    )
    assert build_trigger_config_commands(config) == [
        "TRIGGER:A:TYPE LOGIC",
        "TRIGGER:A:LOGIC:CLASS LOGIC",
        "TRIGGER:A:LOGIC:FUNCTION AND",
        "TRIGGER:A:LOGIC:INPUT:CH1 HIGH",
        "TRIGGER:A:LOGIC:INPUT:CH2 LOW",
        "TRIGGER:A:LOGIC:INPUT:CH3 X",
        "TRIGGER:A:LOGIC:INPUT:CH4 X",
        "TRIGGER:A:LOGIC:INPUT:CLOCK:SOURCE NONE",
        "TRIGGER:A:LOGIC:INPUT:CLOCK:EDGE RISE",
        "TRIGGER:A:LOGIC:PATTERN:WHEN TRUE",
    ]


def test_trigger_config_commands_logic_sethold():
    config = TriggerConfig(
        trigger_type="LOGIC",
        logic_class="SETHOLD",
        logic_clock_source="CH1",
        logic_clock_edge="RISE",
        logic_clock_threshold="1.0",
        logic_data_threshold="0.5",
        logic_setup_time="8e-9",
        logic_hold_time="8e-9",
    )
    assert build_trigger_config_commands(config) == [
        "TRIGGER:A:TYPE LOGIC",
        "TRIGGER:A:LOGIC:CLASS SETHOLD",
        "TRIGGER:A:LOGIC:SETHOLD:CLOCK:SOURCE CH1",
        "TRIGGER:A:LOGIC:SETHOLD:CLOCK:EDGE RISE",
        "TRIGGER:A:LOGIC:SETHOLD:CLOCK:THRESHOLD 1",
        "TRIGGER:A:LOGIC:SETHOLD:DATA:THRESHOLD 0.5",
        "TRIGGER:A:LOGIC:SETHOLD:SETTIME 8e-09",
        "TRIGGER:A:LOGIC:SETHOLD:HOLDTIME 8e-09",
    ]


def test_trigger_config_rejects_invalid_logic_class():
    with pytest.raises(ValueError):
        build_trigger_config_commands(TriggerConfig(trigger_type="LOGIC", logic_class="BOGUS"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("logic_function", "XOR"),
        ("logic_input_ch1", "DONTCARE"),
        ("logic_clock_source", "AUX"),
        ("logic_clock_edge", "EITHER"),
        ("logic_when", "SIDEWAYS"),
    ],
)
def test_trigger_config_rejects_invalid_logic_pattern_enum_values(field, value):
    with pytest.raises(ValueError):
        build_trigger_config_commands(
            TriggerConfig(trigger_type="LOGIC", logic_class="LOGIC", **{field: value})
        )


def test_trigger_config_queries_logic_sethold():
    assert build_trigger_config_queries("LOGIC", logic_class="SETHOLD") == {
        "logic_clock_source": "TRIGGER:A:LOGIC:SETHOLD:CLOCK:SOURCE?",
        "logic_clock_edge": "TRIGGER:A:LOGIC:SETHOLD:CLOCK:EDGE?",
        "logic_clock_threshold": "TRIGGER:A:LOGIC:SETHOLD:CLOCK:THRESHOLD?",
        "logic_data_threshold": "TRIGGER:A:LOGIC:SETHOLD:DATA:THRESHOLD?",
        "logic_setup_time": "TRIGGER:A:LOGIC:SETHOLD:SETTIME?",
        "logic_hold_time": "TRIGGER:A:LOGIC:SETHOLD:HOLDTIME?",
    }


def test_trigger_config_queries_logic_without_class_is_empty():
    assert build_trigger_config_queries("LOGIC") == {}
