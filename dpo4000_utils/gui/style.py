"""Shared Tk/ttk styling helpers for the GUI."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable


COMBOBOX_STYLE_NAME = "App.TCombobox"
COMBOBOX_FIELD_BACKGROUND = "#0f172a"
COMBOBOX_FIELD_FOREGROUND = "#f9fafb"
COMBOBOX_BUTTON_BACKGROUND = "#374151"
COMBOBOX_SELECTED_BACKGROUND = "#2563eb"
COMBOBOX_SELECTED_FOREGROUND = "#ffffff"
COMBOBOX_POPUP_BACKGROUND = "#1f2937"
COMBOBOX_POPUP_FOREGROUND = "#f9fafb"
COMBOBOX_POPUP_ACTIVE_BACKGROUND = "#2563eb"
COMBOBOX_POPUP_ACTIVE_FOREGROUND = "#ffffff"

RADIOBUTTON_STYLE_NAME = "App.TRadiobutton"
RADIOBUTTON_BACKGROUND = "#1f2937"
RADIOBUTTON_ACTIVE_BACKGROUND = "#374151"
RADIOBUTTON_SELECTED_BACKGROUND = "#2563eb"
RADIOBUTTON_FOREGROUND = "#e5e7eb"
RADIOBUTTON_SELECTED_FOREGROUND = "#ffffff"
RADIOBUTTON_DISABLED_FOREGROUND = "#6b7280"
RADIOBUTTON_STYLE_OPTIONS = {
    "background": RADIOBUTTON_BACKGROUND,
    "foreground": RADIOBUTTON_FOREGROUND,
    "padding": (8, 5),
    "font": ("Segoe UI", 10),
}
RADIOBUTTON_STATE_MAP = {
    "background": [
        ("active", RADIOBUTTON_ACTIVE_BACKGROUND),
        ("selected", RADIOBUTTON_SELECTED_BACKGROUND),
    ],
    "foreground": [
        ("disabled", RADIOBUTTON_DISABLED_FOREGROUND),
        ("selected", RADIOBUTTON_SELECTED_FOREGROUND),
        ("active", RADIOBUTTON_SELECTED_FOREGROUND),
    ],
}

# Keep ttk styling deliberately simple. A previous full state-map override made
# Windows/Tk combobox popups unreliable. The app now uses normal combobox state
# for themed selector fields and locks keyboard editing where selection-only
# behavior is required.
COMBOBOX_STYLE_OPTIONS = {
    "fieldbackground": COMBOBOX_FIELD_BACKGROUND,
    "background": COMBOBOX_BUTTON_BACKGROUND,
    "foreground": COMBOBOX_FIELD_FOREGROUND,
    "selectbackground": COMBOBOX_SELECTED_BACKGROUND,
    "selectforeground": COMBOBOX_SELECTED_FOREGROUND,
    "arrowcolor": COMBOBOX_FIELD_FOREGROUND,
    "insertcolor": COMBOBOX_FIELD_FOREGROUND,
    "padding": 6,
}


THEMED_SELECTOR_BLOCKED_EVENTS = (
    "<KeyPress>",
    "<Control-v>",
    "<Control-V>",
    "<BackSpace>",
    "<Delete>",
)


def apply_readable_combobox_style(widget) -> None:
    """Apply the dark application combobox and mode-selector styles."""
    style = ttk.Style(widget)
    style.configure("TCombobox", **COMBOBOX_STYLE_OPTIONS)
    style.configure(COMBOBOX_STYLE_NAME, **COMBOBOX_STYLE_OPTIONS)
    style.configure(RADIOBUTTON_STYLE_NAME, **RADIOBUTTON_STYLE_OPTIONS)
    style.map(RADIOBUTTON_STYLE_NAME, **RADIOBUTTON_STATE_MAP)


def themed_combobox(
    parent: tk.Widget,
    *,
    textvariable: tk.Variable,
    values: Iterable[str] = (),
    readonly: bool = True,
    width: int | None = None,
    postcommand: Callable[[], None] | None = None,
    **kwargs,
) -> ttk.Combobox:
    """Create a dark themed combobox without breaking native popup behavior.

    Windows/Tk may render ``state='readonly'`` with a light system field that
    ignores dark-theme foreground colors. To keep selectors readable and themed,
    selection-only comboboxes use normal state with keyboard edits blocked. The
    native dropdown popup still opens normally and the popup listbox is themed
    after Tk creates it.
    """
    combo = ttk.Combobox(
        parent,
        textvariable=textvariable,
        values=tuple(values),
        state="normal",
        style=COMBOBOX_STYLE_NAME,
        **({"width": width} if width is not None else {}),
        **kwargs,
    )

    if readonly:
        for sequence in THEMED_SELECTOR_BLOCKED_EVENTS:
            combo.bind(sequence, _block_keyboard_edit)

    def _post_dropdown() -> None:
        if postcommand is not None:
            postcommand()
        combo.after_idle(lambda: _theme_combobox_popup(combo))

    combo.configure(postcommand=_post_dropdown)
    return combo


def themed_radiobutton(
    parent: tk.Widget,
    *,
    text: str,
    value: str,
    variable: tk.Variable,
    command: Callable[[], None] | None = None,
    **kwargs,
) -> ttk.Radiobutton:
    """Create a radio button that matches the dark application theme."""
    return ttk.Radiobutton(
        parent,
        text=text,
        value=value,
        variable=variable,
        command=command,
        style=RADIOBUTTON_STYLE_NAME,
        **kwargs,
    )


def _block_keyboard_edit(_event=None) -> str:
    return "break"


def _theme_combobox_popup(combo: ttk.Combobox) -> None:
    """Theme the native combobox popup listbox after Tk creates it.

    The internal popdown path is provided by Tk itself. If a platform/theme does
    not expose the expected listbox, the function quietly leaves native popup
    styling unchanged instead of preventing the dropdown from opening.
    """
    try:
        popdown = combo.tk.call("ttk::combobox::PopdownWindow", str(combo))
        listbox = f"{popdown}.f.l"
        combo.tk.call(
            listbox,
            "configure",
            "-background",
            COMBOBOX_POPUP_BACKGROUND,
            "-foreground",
            COMBOBOX_POPUP_FOREGROUND,
            "-selectbackground",
            COMBOBOX_POPUP_ACTIVE_BACKGROUND,
            "-selectforeground",
            COMBOBOX_POPUP_ACTIVE_FOREGROUND,
            "-activestyle",
            "none",
        )
    except tk.TclError:
        return


__all__ = [
    "COMBOBOX_FIELD_BACKGROUND",
    "COMBOBOX_FIELD_FOREGROUND",
    "COMBOBOX_POPUP_ACTIVE_BACKGROUND",
    "COMBOBOX_POPUP_ACTIVE_FOREGROUND",
    "COMBOBOX_POPUP_BACKGROUND",
    "COMBOBOX_POPUP_FOREGROUND",
    "COMBOBOX_SELECTED_BACKGROUND",
    "COMBOBOX_SELECTED_FOREGROUND",
    "COMBOBOX_STYLE_NAME",
    "COMBOBOX_STYLE_OPTIONS",
    "RADIOBUTTON_ACTIVE_BACKGROUND",
    "RADIOBUTTON_BACKGROUND",
    "RADIOBUTTON_DISABLED_FOREGROUND",
    "RADIOBUTTON_FOREGROUND",
    "RADIOBUTTON_SELECTED_BACKGROUND",
    "RADIOBUTTON_SELECTED_FOREGROUND",
    "RADIOBUTTON_STATE_MAP",
    "RADIOBUTTON_STYLE_NAME",
    "RADIOBUTTON_STYLE_OPTIONS",
    "THEMED_SELECTOR_BLOCKED_EVENTS",
    "apply_readable_combobox_style",
    "themed_combobox",
    "themed_radiobutton",
]
