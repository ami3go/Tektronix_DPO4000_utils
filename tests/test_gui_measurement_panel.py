from dpo4000_utils.control import MEASUREMENT_TYPES_BY_GROUP
from dpo4000_utils.gui.measurement_panel import MEASUREMENT_HELP_TEXT, MEASUREMENT_TAB_TITLE


def test_measurement_panel_exports_expected_copy():
    assert MEASUREMENT_TAB_TITLE == "Measurement"
    assert "MEAS1..MEAS8" in MEASUREMENT_HELP_TEXT


def test_measurement_groups_include_common_submenus():
    assert "Amplitude" in MEASUREMENT_TYPES_BY_GROUP
    assert "Timing" in MEASUREMENT_TYPES_BY_GROUP
    assert "Area / count" in MEASUREMENT_TYPES_BY_GROUP
    assert "FREQUENCY" in MEASUREMENT_TYPES_BY_GROUP["Timing"]
    assert "AMPLITUDE" in MEASUREMENT_TYPES_BY_GROUP["Amplitude"]
