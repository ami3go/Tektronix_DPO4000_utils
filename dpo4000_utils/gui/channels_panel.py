"""Channel-label tab builder for the Tkinter GUI."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

CHANNEL_TITLE = "Channel labels"
CHANNEL_NUMBERS = (1, 2, 3, 4)


def build_channels_card(gui, parent: tk.Widget) -> None:
    """Build the Channels tab contents.

    The parent ``gui`` object owns Tk variables and callbacks. Keeping this
    builder separate lets the monolithic window shrink without changing runtime
    behavior.
    """
    card = gui._card(parent)
    card.pack(fill=tk.X, pady=(0, 10))
    gui._section_title(card, CHANNEL_TITLE)

    grid = ttk.Frame(card, style="Card.TFrame")
    grid.pack(fill=tk.X, padx=14, pady=(8, 12))

    for channel in CHANNEL_NUMBERS:
        ttk.Label(grid, text=f"CH{channel}", style="Card.TLabel", width=5).grid(
            row=channel - 1,
            column=0,
            sticky="w",
            pady=4,
        )
        ttk.Entry(grid, textvariable=gui.label_vars[channel], width=30).grid(
            row=channel - 1,
            column=1,
            sticky="ew",
            padx=(8, 0),
            pady=4,
        )
    grid.columnconfigure(1, weight=1)

    buttons = ttk.Frame(card, style="Card.TFrame")
    buttons.pack(fill=tk.X, padx=14, pady=(0, 14))
    ttk.Button(buttons, text="Read labels", command=gui.read_labels).pack(side=tk.LEFT)
    ttk.Button(buttons, text="Apply labels", style="Accent.TButton", command=gui.apply_labels).pack(
        side=tk.LEFT,
        padx=(8, 0),
    )


__all__ = ["CHANNEL_NUMBERS", "CHANNEL_TITLE", "build_channels_card"]
