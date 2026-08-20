"""Shared Tk/ttk styling helpers for the GUI."""

from __future__ import annotations

from tkinter import ttk


COMBOBOX_FIELD_BACKGROUND = "#e5e7eb"
COMBOBOX_FIELD_FOREGROUND = "#111827"
COMBOBOX_SELECTED_BACKGROUND = "#2563eb"
COMBOBOX_SELECTED_FOREGROUND = "#ffffff"

# Keep combobox styling deliberately minimal. Windows/Tk can break readonly
# combobox popup behavior when a full state map or popup Listbox option database
# override is applied. A plain configure() keeps dropdown mechanics native while
# making the selected value readable on the light system field.
COMBOBOX_STYLE_OPTIONS = {
    "fieldbackground": COMBOBOX_FIELD_BACKGROUND,
    "background": COMBOBOX_FIELD_BACKGROUND,
    "foreground": COMBOBOX_FIELD_FOREGROUND,
    "selectbackground": COMBOBOX_SELECTED_BACKGROUND,
    "selectforeground": COMBOBOX_SELECTED_FOREGROUND,
    "padding": 6,
}


def apply_readable_combobox_style(widget) -> None:
    """Apply readable combobox field colors without overriding popup behavior."""
    style = ttk.Style(widget)
    style.configure("TCombobox", **COMBOBOX_STYLE_OPTIONS)


__all__ = [
    "COMBOBOX_FIELD_BACKGROUND",
    "COMBOBOX_FIELD_FOREGROUND",
    "COMBOBOX_SELECTED_BACKGROUND",
    "COMBOBOX_SELECTED_FOREGROUND",
    "COMBOBOX_STYLE_OPTIONS",
    "apply_readable_combobox_style",
]
