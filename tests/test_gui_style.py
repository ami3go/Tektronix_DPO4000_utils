from dpo4000_utils.gui.style import (
    COMBOBOX_FIELD_BACKGROUND,
    COMBOBOX_FIELD_FOREGROUND,
    COMBOBOX_POPUP_ACTIVE_BACKGROUND,
    COMBOBOX_POPUP_ACTIVE_FOREGROUND,
    COMBOBOX_POPUP_BACKGROUND,
    COMBOBOX_POPUP_FOREGROUND,
    COMBOBOX_SELECTED_BACKGROUND,
    COMBOBOX_SELECTED_FOREGROUND,
    COMBOBOX_STYLE_NAME,
    COMBOBOX_STYLE_OPTIONS,
    THEMED_SELECTOR_BLOCKED_EVENTS,
)


def test_combobox_style_uses_application_dark_field():
    assert COMBOBOX_STYLE_NAME == "App.TCombobox"
    assert COMBOBOX_STYLE_OPTIONS["fieldbackground"] == COMBOBOX_FIELD_BACKGROUND
    assert COMBOBOX_STYLE_OPTIONS["foreground"] == COMBOBOX_FIELD_FOREGROUND
    assert COMBOBOX_FIELD_BACKGROUND == "#0f172a"
    assert COMBOBOX_FIELD_FOREGROUND == "#f9fafb"


def test_combobox_style_keeps_state_map_out_of_style_options():
    # Do not use a full ttk state map here; it made Windows readonly combobox
    # dropdowns unreliable. The themed factory locks selector edits instead.
    assert "map" not in COMBOBOX_STYLE_OPTIONS
    assert COMBOBOX_STYLE_OPTIONS["selectbackground"] == COMBOBOX_SELECTED_BACKGROUND
    assert COMBOBOX_STYLE_OPTIONS["selectforeground"] == COMBOBOX_SELECTED_FOREGROUND


def test_combobox_popup_colors_follow_dark_theme_constants():
    assert COMBOBOX_POPUP_BACKGROUND == "#1f2937"
    assert COMBOBOX_POPUP_FOREGROUND == "#f9fafb"
    assert COMBOBOX_POPUP_ACTIVE_BACKGROUND == "#2563eb"
    assert COMBOBOX_POPUP_ACTIVE_FOREGROUND == "#ffffff"


def test_selector_combobox_blocks_typing_but_not_mouse_dropdown():
    assert "<KeyPress>" in THEMED_SELECTOR_BLOCKED_EVENTS
    assert "<Button-1>" not in THEMED_SELECTOR_BLOCKED_EVENTS
