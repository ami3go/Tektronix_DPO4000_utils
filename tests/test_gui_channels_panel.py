from dpo4000_utils.gui.channels_panel import CHANNEL_NUMBERS, CHANNEL_TITLE


def test_channels_panel_exports_expected_channels():
    assert CHANNEL_TITLE == "Channel labels"
    assert CHANNEL_NUMBERS == (1, 2, 3, 4)
