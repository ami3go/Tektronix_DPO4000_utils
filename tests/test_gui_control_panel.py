from dpo4000_utils.control import MEASUREMENT_TYPES_BY_GROUP, TRIGGER_COUPLINGS, TRIGGER_SLOPES
from dpo4000_utils.gui.control_panel import (
    CONTROL_TAB_TITLE,
    HORIZONTAL_HELP_TEXT,
    MEASUREMENT_HELP_TEXT,
    TRIGGER_HELP_TEXT,
)


def test_control_panel_exports_expected_copy():
    assert CONTROL_TAB_TITLE == "Control"
    assert "MEAS1..MEAS8" in MEASUREMENT_HELP_TEXT
    assert "HORIZONTAL:POSITION" in HORIZONTAL_HELP_TEXT
    assert "A-trigger" in TRIGGER_HELP_TEXT


def test_control_measurement_groups_include_common_submenus():
    assert "Amplitude" in MEASUREMENT_TYPES_BY_GROUP
    assert "Timing" in MEASUREMENT_TYPES_BY_GROUP
    assert "Area / count" in MEASUREMENT_TYPES_BY_GROUP
    assert "FREQUENCY" in MEASUREMENT_TYPES_BY_GROUP["Timing"]
    assert "AMPLITUDE" in MEASUREMENT_TYPES_BY_GROUP["Amplitude"]


def test_control_trigger_options_include_common_choices():
    assert "RISE" in TRIGGER_SLOPES
    assert "FALL" in TRIGGER_SLOPES
    assert "DC" in TRIGGER_COUPLINGS
