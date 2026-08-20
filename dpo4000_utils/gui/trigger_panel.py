"""Trigger tab builder for trigger level, horizontal position, and acquisition controls."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..control import TRIGGER_COUPLINGS, TRIGGER_MODES, TRIGGER_SLOPES, TRIGGER_SOURCES


TRIGGER_CHANNELS = ("1", "2", "3", "4")
TRIGGER_LEVEL_HINT = "Numeric volts, or Tektronix presets TTL/ECL."
HORIZONTAL_TRIGGER_HINT = "Move horizontal trigger position. Values use the scope SCPI HORIZONTAL:POSITION units."
EDGE_TRIGGER_HINT = "Common A edge-trigger setup: mode, source, slope, coupling, and level."
ACQUISITION_HINT = "Run, stop, single-shot, continuous acquisition, or force one trigger event."


def build_trigger_card(gui, parent: tk.Widget) -> None:
    """Build the Trigger tab using the owning GUI object for state/actions."""
    outer = ttk.Frame(parent)
    outer.pack(fill=tk.BOTH, expand=True)

    canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0, bg="#111827")
    scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
    body = ttk.Frame(canvas)

    window_id = canvas.create_window((0, 0), window=body, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    body.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))

    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    build_quick_trigger_level_section(gui, body)
    build_horizontal_position_section(gui, body)
    build_edge_trigger_section(gui, body)
    build_acquisition_section(gui, body)


def _card(gui, parent: tk.Widget, title: str, help_text: str | None = None) -> ttk.Frame:
    card = gui._card(parent)
    card.pack(fill=tk.X, pady=(0, 10))
    gui._section_title(card, title)
    if help_text:
        ttk.Label(
            card,
            text=help_text,
            style="Muted.TLabel",
            wraplength=360,
            justify=tk.LEFT,
        ).pack(fill=tk.X, padx=14, pady=(0, 8))
    return card


def _row(parent: tk.Widget) -> ttk.Frame:
    row = ttk.Frame(parent, style="Card.TFrame")
    row.pack(fill=tk.X, padx=14, pady=(0, 8))
    return row


def _field_label(parent: tk.Widget, text: str) -> None:
    ttk.Label(parent, text=text, style="Card.TLabel").pack(anchor="w", pady=(0, 2))


def build_quick_trigger_level_section(gui, parent: tk.Widget) -> None:
    card = _card(gui, parent, "Trigger level", TRIGGER_LEVEL_HINT)

    body = ttk.Frame(card, style="Card.TFrame")
    body.pack(fill=tk.X, padx=14, pady=(0, 14))

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


def build_horizontal_position_section(gui, parent: tk.Widget) -> None:
    card = _card(gui, parent, "Horizontal trigger position", HORIZONTAL_TRIGGER_HINT)

    row = _row(card)
    _field_label(row, "Horizontal position")
    ttk.Entry(row, textvariable=gui.horizontal_position_var).pack(fill=tk.X)

    row = _row(card)
    ttk.Button(row, text="Set position", style="Accent.TButton", command=gui.set_horizontal_position).pack(
        side=tk.LEFT,
        fill=tk.X,
        expand=True,
    )
    ttk.Button(row, text="Read", command=gui.read_horizontal_position).pack(
        side=tk.LEFT,
        fill=tk.X,
        expand=True,
        padx=(8, 0),
    )

    row = _row(card)
    for label, delta in (("◀◀ -10", -10), ("◀ -1", -1), ("Center 0", 0), ("+1 ▶", 1), ("+10 ▶▶", 10)):
        command = (
            lambda step=delta: gui.set_horizontal_position_to_zero()
            if step == 0
            else gui.nudge_horizontal_position(step)
        )
        ttk.Button(row, text=label, command=command).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))


def build_edge_trigger_section(gui, parent: tk.Widget) -> None:
    card = _card(gui, parent, "Edge trigger setup", EDGE_TRIGGER_HINT)

    row = _row(card)
    mode_col = ttk.Frame(row, style="Card.TFrame")
    mode_col.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
    _field_label(mode_col, "Mode")
    ttk.Combobox(mode_col, textvariable=gui.control_trigger_mode_var, values=TRIGGER_MODES, state="readonly").pack(fill=tk.X)

    source_col = ttk.Frame(row, style="Card.TFrame")
    source_col.pack(side=tk.LEFT, fill=tk.X, expand=True)
    _field_label(source_col, "Source")
    ttk.Combobox(source_col, textvariable=gui.control_trigger_source_var, values=TRIGGER_SOURCES, state="readonly").pack(fill=tk.X)

    row = _row(card)
    slope_col = ttk.Frame(row, style="Card.TFrame")
    slope_col.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
    _field_label(slope_col, "Slope")
    ttk.Combobox(slope_col, textvariable=gui.control_trigger_slope_var, values=TRIGGER_SLOPES, state="readonly").pack(fill=tk.X)

    coupling_col = ttk.Frame(row, style="Card.TFrame")
    coupling_col.pack(side=tk.LEFT, fill=tk.X, expand=True)
    _field_label(coupling_col, "Coupling")
    ttk.Combobox(coupling_col, textvariable=gui.control_trigger_coupling_var, values=TRIGGER_COUPLINGS, state="readonly").pack(fill=tk.X)

    row = _row(card)
    _field_label(row, "Level")
    ttk.Entry(row, textvariable=gui.control_trigger_level_var).pack(fill=tk.X)

    row = _row(card)
    ttk.Button(
        row,
        text="Apply edge trigger",
        style="Accent.TButton",
        command=gui.apply_edge_trigger_controls,
    ).pack(fill=tk.X)


def build_acquisition_section(gui, parent: tk.Widget) -> None:
    card = _card(gui, parent, "Acquisition / trigger actions", ACQUISITION_HINT)

    row = _row(card)
    for text, command in (
        ("Run", gui.run_acquisition),
        ("Stop", gui.stop_acquisition),
        ("Single", gui.single_acquisition),
        ("Continuous", gui.continuous_acquisition),
    ):
        ttk.Button(row, text=text, command=command).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

    row = _row(card)
    ttk.Button(row, text="Force trigger", style="Accent.TButton", command=gui.force_trigger_event).pack(fill=tk.X)


__all__ = [
    "ACQUISITION_HINT",
    "EDGE_TRIGGER_HINT",
    "HORIZONTAL_TRIGGER_HINT",
    "TRIGGER_CHANNELS",
    "TRIGGER_LEVEL_HINT",
    "build_trigger_card",
]
