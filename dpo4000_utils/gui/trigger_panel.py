"""Trigger tab builder for the Tkinter GUI."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


TRIGGER_CHANNELS = ("1", "2", "3", "4")
TRIGGER_LEVEL_HINT = "Numeric volts, or Tektronix presets TTL/ECL."


def build_trigger_card(gui, parent: tk.Widget) -> None:
    """Build the Trigger tab using the owning GUI object for state/actions."""
    card = gui._card(parent)
    card.pack(fill=tk.X, pady=(0, 10))
    gui._section_title(card, "Trigger")

    body = ttk.Frame(card, style="Card.TFrame")
    body.pack(fill=tk.X, padx=14, pady=(8, 14))

    row = ttk.Frame(body, style="Card.TFrame")
    row.pack(fill=tk.X, pady=(0, 8))

    ttk.Label(row, text="Source", style="Card.TLabel").pack(side=tk.LEFT)
    ttk.Combobox(
        row,
        textvariable=gui.trigger_setup_channel_var,
        width=7,
        state="readonly",
        values=TRIGGER_CHANNELS,
    ).pack(side=tk.LEFT, padx=(8, 14))

    ttk.Label(row, text="Level V", style="Card.TLabel").pack(side=tk.LEFT)
    ttk.Entry(row, textvariable=gui.trigger_level_var, width=12).pack(
        side=tk.LEFT,
        padx=(8, 0),
        fill=tk.X,
        expand=True,
    )

    ttk.Checkbutton(
        body,
        text="Set edge trigger source to selected channel",
        variable=gui.trigger_set_source_var,
    ).pack(anchor="w", pady=(0, 8))

    ttk.Label(
        body,
        text=TRIGGER_LEVEL_HINT,
        style="Muted.TLabel",
        wraplength=360,
        justify=tk.LEFT,
    ).pack(fill=tk.X, pady=(0, 8))

    readback_row = ttk.Frame(body, style="Card.TFrame")
    readback_row.pack(fill=tk.X, pady=(0, 8))
    ttk.Label(readback_row, text="Readback", style="Card.TLabel").pack(side=tk.LEFT)
    ttk.Entry(
        readback_row,
        textvariable=gui.trigger_readback_var,
        width=16,
        state="readonly",
    ).pack(side=tk.LEFT, padx=(8, 0), fill=tk.X, expand=True)

    buttons = ttk.Frame(body, style="Card.TFrame")
    buttons.pack(fill=tk.X)
    ttk.Button(buttons, text="Read trigger level", command=gui.read_trigger_level).pack(
        side=tk.LEFT,
        fill=tk.X,
        expand=True,
    )
    ttk.Button(
        buttons,
        text="Set trigger level",
        style="Accent.TButton",
        command=gui.apply_trigger_level,
    ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))


__all__ = ["TRIGGER_CHANNELS", "TRIGGER_LEVEL_HINT", "build_trigger_card"]
