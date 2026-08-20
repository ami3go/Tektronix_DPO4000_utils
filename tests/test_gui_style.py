from dpo4000_utils.gui.style import (
    COMBOBOX_FIELD_BACKGROUND,
    COMBOBOX_FIELD_FOREGROUND,
    COMBOBOX_SELECTED_BACKGROUND,
    COMBOBOX_SELECTED_FOREGROUND,
    COMBOBOX_STYLE_OPTIONS,
)


def test_combobox_style_uses_dark_text_on_light_field():
    assert COMBOBOX_STYLE_OPTIONS["fieldbackground"] == COMBOBOX_FIELD_BACKGROUND
    assert COMBOBOX_STYLE_OPTIONS["foreground"] == COMBOBOX_FIELD_FOREGROUND
    assert COMBOBOX_FIELD_BACKGROUND != COMBOBOX_FIELD_FOREGROUND
    assert COMBOBOX_FIELD_FOREGROUND == "#111827"


def test_combobox_style_keeps_native_popup_behavior():
    # Do not use ttk state maps or popup Listbox option database overrides here.
    # They made Windows readonly combobox dropdowns stop behaving normally.
    assert "map" not in COMBOBOX_STYLE_OPTIONS
    assert "popdown" not in COMBOBOX_STYLE_OPTIONS
    assert COMBOBOX_STYLE_OPTIONS["selectbackground"] == COMBOBOX_SELECTED_BACKGROUND
    assert COMBOBOX_STYLE_OPTIONS["selectforeground"] == COMBOBOX_SELECTED_FOREGROUND
