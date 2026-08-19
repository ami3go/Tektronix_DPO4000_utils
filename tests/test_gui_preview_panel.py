from dpo4000_utils.gui.preview_panel import (
    POST_IMAGE_TRIGGER_VALUES,
    PREVIEW_COPY_HINT,
    PREVIEW_EMPTY_TEXT,
    PREVIEW_TITLE,
)


def test_preview_panel_exports_expected_text():
    assert PREVIEW_TITLE == "Screen preview"
    assert "Capture preview" in PREVIEW_EMPTY_TEXT
    assert "Ctrl+C" in PREVIEW_COPY_HINT
    assert POST_IMAGE_TRIGGER_VALUES == ("", "1", "2", "3", "4")
