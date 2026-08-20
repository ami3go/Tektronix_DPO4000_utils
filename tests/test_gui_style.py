from dpo4000_utils.gui.style import (
    COMBOBOX_FIELD_BACKGROUND,
    COMBOBOX_FIELD_FOREGROUND,
    COMBOBOX_POPUP_OPTIONS,
    COMBOBOX_STATE_MAP,
    COMBOBOX_STYLE_OPTIONS,
)


def test_combobox_style_uses_dark_text_on_light_field():
    assert COMBOBOX_STYLE_OPTIONS["fieldbackground"] == COMBOBOX_FIELD_BACKGROUND
    assert COMBOBOX_STYLE_OPTIONS["foreground"] == COMBOBOX_FIELD_FOREGROUND
    assert COMBOBOX_FIELD_BACKGROUND != COMBOBOX_FIELD_FOREGROUND
    assert COMBOBOX_FIELD_FOREGROUND == "#111827"


def test_combobox_readonly_state_keeps_text_visible():
    readonly_foreground = dict(COMBOBOX_STATE_MAP["foreground"])["readonly"]
    readonly_background = dict(COMBOBOX_STATE_MAP["fieldbackground"])["readonly"]
    assert readonly_foreground == COMBOBOX_FIELD_FOREGROUND
    assert readonly_background == COMBOBOX_FIELD_BACKGROUND


def test_combobox_popup_listbox_uses_matching_visible_colors():
    assert COMBOBOX_POPUP_OPTIONS["*TCombobox*Listbox.foreground"] == COMBOBOX_FIELD_FOREGROUND
    assert COMBOBOX_POPUP_OPTIONS["*TCombobox*Listbox.background"] != COMBOBOX_FIELD_FOREGROUND
