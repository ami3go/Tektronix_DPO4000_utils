from dpo4000_utils.gui.settings_panel import FILENAME_FORMAT_HINT, NAMING_SECTIONS, SETTINGS_TITLE


def test_settings_panel_exports_expected_text():
    assert SETTINGS_TITLE == "Output and scope settings"
    assert "<prefix><base>" in FILENAME_FORMAT_HINT
    assert NAMING_SECTIONS == ("PNG images", "CSV waveforms", "Settings JSON")
