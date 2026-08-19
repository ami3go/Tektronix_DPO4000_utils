from dpo4000_utils.gui.trigger_panel import TRIGGER_CHANNELS, TRIGGER_LEVEL_HINT


def test_trigger_panel_exports_expected_channels():
    assert TRIGGER_CHANNELS == ("1", "2", "3", "4")


def test_trigger_panel_hint_mentions_supported_presets():
    assert "TTL" in TRIGGER_LEVEL_HINT
    assert "ECL" in TRIGGER_LEVEL_HINT
