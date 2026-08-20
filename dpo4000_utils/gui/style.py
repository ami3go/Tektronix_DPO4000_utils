"""Shared Tk/ttk styling helpers for the GUI."""

from __future__ import annotations

from tkinter import ttk


COMBOBOX_FIELD_BACKGROUND = "#e5e7eb"
COMBOBOX_FIELD_FOREGROUND = "#111827"
COMBOBOX_DISABLED_BACKGROUND = "#9ca3af"
COMBOBOX_DISABLED_FOREGROUND = "#374151"
COMBOBOX_SELECTED_BACKGROUND = "#2563eb"
COMBOBOX_SELECTED_FOREGROUND = "#ffffff"
COMBOBOX_POPUP_BACKGROUND = "#f9fafb"
COMBOBOX_POPUP_FOREGROUND = "#111827"

# Windows/Tk can ignore parts of dark combobox styling in readonly state and
# leave the field light. Use an intentionally light combobox field with dark
# text so values remain readable on every supported platform/theme.
COMBOBOX_STYLE_OPTIONS = {
    "fieldbackground": COMBOBOX_FIELD_BACKGROUND,
    "background": COMBOBOX_FIELD_BACKGROUND,
    "foreground": COMBOBOX_FIELD_FOREGROUND,
    "selectbackground": COMBOBOX_SELECTED_BACKGROUND,
    "selectforeground": COMBOBOX_SELECTED_FOREGROUND,
    "arrowcolor": COMBOBOX_FIELD_FOREGROUND,
}

COMBOBOX_STATE_MAP = {
    "fieldbackground": [
        ("disabled", COMBOBOX_DISABLED_BACKGROUND),
        ("readonly", COMBOBOX_FIELD_BACKGROUND),
        ("focus", COMBOBOX_FIELD_BACKGROUND),
        ("!disabled", COMBOBOX_FIELD_BACKGROUND),
    ],
    "background": [
        ("disabled", COMBOBOX_DISABLED_BACKGROUND),
        ("readonly", COMBOBOX_FIELD_BACKGROUND),
        ("active", COMBOBOX_FIELD_BACKGROUND),
        ("!disabled", COMBOBOX_FIELD_BACKGROUND),
    ],
    "foreground": [
        ("disabled", COMBOBOX_DISABLED_FOREGROUND),
        ("readonly", COMBOBOX_FIELD_FOREGROUND),
        ("focus", COMBOBOX_FIELD_FOREGROUND),
        ("!disabled", COMBOBOX_FIELD_FOREGROUND),
    ],
    "selectbackground": [
        ("readonly", COMBOBOX_SELECTED_BACKGROUND),
        ("focus", COMBOBOX_SELECTED_BACKGROUND),
    ],
    "selectforeground": [
        ("readonly", COMBOBOX_SELECTED_FOREGROUND),
        ("focus", COMBOBOX_SELECTED_FOREGROUND),
    ],
    "arrowcolor": [
        ("disabled", COMBOBOX_DISABLED_FOREGROUND),
        ("!disabled", COMBOBOX_FIELD_FOREGROUND),
    ],
}

COMBOBOX_POPUP_OPTIONS = {
    "*TCombobox*Listbox.background": COMBOBOX_POPUP_BACKGROUND,
    "*TCombobox*Listbox.foreground": COMBOBOX_POPUP_FOREGROUND,
    "*TCombobox*Listbox.selectBackground": COMBOBOX_SELECTED_BACKGROUND,
    "*TCombobox*Listbox.selectForeground": COMBOBOX_SELECTED_FOREGROUND,
    "*TCombobox*Listbox.font": "Segoe UI 10",
}


def apply_readable_combobox_style(widget) -> None:
    """Apply readable combobox field and popup colors.

    Some Windows Tk themes keep readonly combobox fields light even when the
    surrounding GUI uses a dark theme. This helper chooses a light field with
    dark text and also styles the dropdown listbox so the selected values stay
    readable instead of white-on-light.
    """
    style = ttk.Style(widget)
    style.configure("TCombobox", **COMBOBOX_STYLE_OPTIONS)
    style.map("TCombobox", **COMBOBOX_STATE_MAP)

    for option, value in COMBOBOX_POPUP_OPTIONS.items():
        widget.option_add(option, value)


__all__ = [
    "COMBOBOX_FIELD_BACKGROUND",
    "COMBOBOX_FIELD_FOREGROUND",
    "COMBOBOX_POPUP_OPTIONS",
    "COMBOBOX_STATE_MAP",
    "COMBOBOX_STYLE_OPTIONS",
    "apply_readable_combobox_style",
]
