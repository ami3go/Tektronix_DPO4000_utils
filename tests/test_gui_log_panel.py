from dpo4000_utils.gui.log_panel import LOG_FONT, LOG_HEIGHT_LINES, LOG_TITLE


def test_log_panel_exports_expected_defaults():
    assert LOG_TITLE == "Log"
    assert LOG_HEIGHT_LINES == 7
    assert LOG_FONT == ("Consolas", 9)
