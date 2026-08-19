"""Log tab builder for the Tkinter GUI."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

LOG_TITLE = "Log"
LOG_HEIGHT_LINES = 7
LOG_FONT = ("Consolas", 9)


def build_log(gui, parent: tk.Widget) -> None:
    """Build the Log tab contents and attach ``gui.log_text``."""
    log_card = gui._card(parent)
    log_card.pack(fill=tk.BOTH, expand=True, pady=(0, 0))
    gui._section_title(log_card, LOG_TITLE)
    gui.log_text = tk.Text(
        log_card,
        height=LOG_HEIGHT_LINES,
        bg="#020617",
        fg="#d1d5db",
        insertbackground="#ffffff",
        relief=tk.FLAT,
        wrap=tk.WORD,
        font=LOG_FONT,
    )
    gui.log_text.pack(fill=tk.BOTH, expand=True, padx=14, pady=(8, 14))
    gui.log_text.configure(state=tk.DISABLED)


__all__ = ["LOG_FONT", "LOG_HEIGHT_LINES", "LOG_TITLE", "build_log"]
