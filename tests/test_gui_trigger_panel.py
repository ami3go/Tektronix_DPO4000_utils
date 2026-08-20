from dpo4000_utils.control import TRIGGER_COUPLINGS, TRIGGER_SLOPES
from dpo4000_utils.gui.trigger_panel import (
    ACQUISITION_HINT,
    EDGE_TRIGGER_HINT,
    HORIZONTAL_TRIGGER_HINT,
    TRIGGER_CHANNELS,
    TRIGGER_LEVEL_HINT,
)


def test_trigger_panel_exports_expected_channels():
    assert TRIGGER_CHANNELS == ("1", "2", "3", "4")


def test_trigger_panel_hint_mentions_supported_presets():
    assert "TTL" in TRIGGER_LEVEL_HINT
    assert "ECL" in TRIGGER_LEVEL_HINT


def test_trigger_panel_includes_horizontal_and_acquisition_controls():
    assert "HORIZONTAL:POSITION" in HORIZONTAL_TRIGGER_HINT
    assert "edge-trigger" in EDGE_TRIGGER_HINT
    assert "Force" not in ACQUISITION_HINT  # hint stays generic; button text is in the builder


def test_trigger_options_include_common_choices():
    assert "RISE" in TRIGGER_SLOPES
    assert "FALL" in TRIGGER_SLOPES
    assert "DC" in TRIGGER_COUPLINGS
