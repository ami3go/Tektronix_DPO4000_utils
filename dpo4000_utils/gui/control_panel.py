"""Control tab builder for measurements, horizontal position, and trigger controls."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..control import (
    MEASUREMENT_SLOTS,
    MEASUREMENT_SOURCES,
    MEASUREMENT_TYPES_BY_GROUP,
    TRIGGER_COUPLINGS,
    TRIGGER_MODES,
    TRIGGER_SLOPES,
    TRIGGER_SOURCES,
)

CONTROL_TAB_TITLE = "Control"
MEASUREMENT_HELP_TEXT = "Add or update displayed MEAS1..MEAS8 readouts on the scope."
HORIZONTAL_HELP_TEXT = "Move horizontal trigger position. Values use the scope SCPI HORIZONTAL:POSITION units."
TRIGGER_HELP_TEXT = "Common A-trigger setup and acquisition buttons. Advanced trigger families can be selected on the scope if needed."


def build_control_tab(gui, parent: tk.Widget) -> None:
    """Build the scrollable Control tab."""
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

    build_measurement_section(gui, body)
    build_horizontal_section(gui, body)
    build_trigger_section(gui, body)


def _card(gui, parent: tk.Widget, title: str, help_text: str) -> ttk.Frame:
    card = gui._card(parent)
    card.pack(fill=tk.X, pady=(0, 10))
    gui._section_title(card, title)
    ttk.Label(
        card,
        text=help_text,
        style="Muted.TLabel",
        wraplength=360,
        justify=tk.LEFT,
    ).pack(fill=tk.X, padx=14, pady=(0, 8))
    return card


def _label(parent: tk.Widget, text: str) -> None:
    ttk.Label(parent, text=text, style="Card.TLabel").pack(anchor="w", pady=(0, 2))


def _row(parent: tk.Widget) -> ttk.Frame:
    row = ttk.Frame(parent, style="Card.TFrame")
    row.pack(fill=tk.X, padx=14, pady=(0, 8))
    return row


def build_measurement_section(gui, parent: tk.Widget) -> None:
    card = _card(gui, parent, "Measurements", MEASUREMENT_HELP_TEXT)

    row = _row(card)
    col = ttk.Frame(row, style="Card.TFrame")
    col.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
    _label(col, "Slot")
    ttk.Combobox(
        col,
        textvariable=gui.measurement_slot_var,
        values=tuple(str(slot) for slot in MEASUREMENT_SLOTS),
        width=7,
        state="readonly",
    ).pack(fill=tk.X)

    col = ttk.Frame(row, style="Card.TFrame")
    col.pack(side=tk.LEFT, fill=tk.X, expand=True)
    _label(col, "Group")
    group_combo = ttk.Combobox(
        col,
        textvariable=gui.measurement_group_var,
        values=tuple(MEASUREMENT_TYPES_BY_GROUP),
        width=16,
        state="readonly",
    )
    group_combo.pack(fill=tk.X)
    group_combo.bind("<<ComboboxSelected>>", gui._on_measurement_group_changed)

    row = _row(card)
    _label(row, "Measurement type")
    measurement_type = ttk.Combobox(
        row,
        textvariable=gui.measurement_type_var,
        values=MEASUREMENT_TYPES_BY_GROUP[gui.measurement_group_var.get()],
        state="normal",
    )
    measurement_type.pack(fill=tk.X)
    gui.measurement_type_combo = measurement_type
    measurement_type.bind("<<ComboboxSelected>>", lambda _event: gui.measurement_type_var.set(gui.measurement_type_var.get().upper()))

    row = _row(card)
    col = ttk.Frame(row, style="Card.TFrame")
    col.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
    _label(col, "Source 1")
    ttk.Combobox(
        col,
        textvariable=gui.measurement_source1_var,
        values=MEASUREMENT_SOURCES,
        state="readonly",
    ).pack(fill=tk.X)

    col = ttk.Frame(row, style="Card.TFrame")
    col.pack(side=tk.LEFT, fill=tk.X, expand=True)
    _label(col, "Source 2")
    ttk.Combobox(
        col,
        textvariable=gui.measurement_source2_var,
        values=("",) + MEASUREMENT_SOURCES,
        state="readonly",
    ).pack(fill=tk.X)

    row = _row(card)
    ttk.Button(row, text="Add / update measurement", style="Accent.TButton", command=gui.add_measurement_to_display).pack(
        side=tk.LEFT,
        fill=tk.X,
        expand=True,
    )
    ttk.Button(row, text="Read value", command=gui.read_measurement_value).pack(
        side=tk.LEFT,
        fill=tk.X,
        expand=True,
        padx=(8, 0),
    )

    row = _row(card)
    ttk.Button(row, text="Clear slot", command=gui.clear_measurement_slot).pack(
        side=tk.LEFT,
        fill=tk.X,
        expand=True,
    )
    ttk.Button(row, text="Clear all measurements", command=gui.clear_all_measurements).pack(
        side=tk.LEFT,
        fill=tk.X,
        expand=True,
        padx=(8, 0),
    )

    row = _row(card)
    _label(row, "Last read value")
    ttk.Entry(row, textvariable=gui.measurement_value_var, state="readonly").pack(fill=tk.X)


def build_horizontal_section(gui, parent: tk.Widget) -> None:
    card = _card(gui, parent, "Horizontal / trigger position", HORIZONTAL_HELP_TEXT)

    row = _row(card)
    _label(row, "Horizontal position")
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
        command = (lambda step=delta: gui.set_horizontal_position_to_zero() if step == 0 else gui.nudge_horizontal_position(step))
        ttk.Button(row, text=label, command=command).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))


def build_trigger_section(gui, parent: tk.Widget) -> None:
    card = _card(gui, parent, "Trigger control", TRIGGER_HELP_TEXT)

    row = _row(card)
    col = ttk.Frame(row, style="Card.TFrame")
    col.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
    _label(col, "Mode")
    ttk.Combobox(col, textvariable=gui.control_trigger_mode_var, values=TRIGGER_MODES, state="readonly").pack(fill=tk.X)

    col = ttk.Frame(row, style="Card.TFrame")
    col.pack(side=tk.LEFT, fill=tk.X, expand=True)
    _label(col, "Source")
    ttk.Combobox(col, textvariable=gui.control_trigger_source_var, values=TRIGGER_SOURCES, state="readonly").pack(fill=tk.X)

    row = _row(card)
    col = ttk.Frame(row, style="Card.TFrame")
    col.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
    _label(col, "Slope")
    ttk.Combobox(col, textvariable=gui.control_trigger_slope_var, values=TRIGGER_SLOPES, state="readonly").pack(fill=tk.X)

    col = ttk.Frame(row, style="Card.TFrame")
    col.pack(side=tk.LEFT, fill=tk.X, expand=True)
    _label(col, "Coupling")
    ttk.Combobox(col, textvariable=gui.control_trigger_coupling_var, values=TRIGGER_COUPLINGS, state="readonly").pack(fill=tk.X)

    row = _row(card)
    _label(row, "Level")
    ttk.Entry(row, textvariable=gui.control_trigger_level_var).pack(fill=tk.X)

    row = _row(card)
    ttk.Button(row, text="Apply edge trigger", style="Accent.TButton", command=gui.apply_edge_trigger_controls).pack(
        side=tk.LEFT,
        fill=tk.X,
        expand=True,
    )
    ttk.Button(row, text="Force trigger", command=gui.force_trigger_event).pack(
        side=tk.LEFT,
        fill=tk.X,
        expand=True,
        padx=(8, 0),
    )

    row = _row(card)
    for text, command in (
        ("Run", gui.run_acquisition),
        ("Stop", gui.stop_acquisition),
        ("Single", gui.single_acquisition),
        ("Continuous", gui.continuous_acquisition),
    ):
        ttk.Button(row, text=text, command=command).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))


__all__ = [
    "CONTROL_TAB_TITLE",
    "HORIZONTAL_HELP_TEXT",
    "MEASUREMENT_HELP_TEXT",
    "TRIGGER_HELP_TEXT",
    "build_control_tab",
]
