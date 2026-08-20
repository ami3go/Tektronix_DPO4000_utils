"""Measurement tab builder for displayed MEAS1..MEAS8 readouts."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..control import MEASUREMENT_SLOTS, MEASUREMENT_SOURCES, MEASUREMENT_TYPES_BY_GROUP
from .style import themed_combobox


MEASUREMENT_TAB_TITLE = "Measurement"
MEASUREMENT_HELP_TEXT = "Add or update displayed MEAS1..MEAS8 readouts on the scope."


def build_measurement_tab(gui, parent: tk.Widget) -> None:
    """Build the Measurement tab."""
    card = gui._card(parent)
    card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
    gui._section_title(card, MEASUREMENT_TAB_TITLE)

    body = ttk.Frame(card, style="Card.TFrame")
    body.pack(fill=tk.BOTH, expand=True, padx=14, pady=(8, 14))

    ttk.Label(
        body,
        text=MEASUREMENT_HELP_TEXT,
        style="Muted.TLabel",
        wraplength=360,
        justify=tk.LEFT,
    ).pack(fill=tk.X, pady=(0, 10))

    row = ttk.Frame(body, style="Card.TFrame")
    row.pack(fill=tk.X, pady=(0, 8))

    slot_col = ttk.Frame(row, style="Card.TFrame")
    slot_col.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
    _field_label(slot_col, "Slot")
    themed_combobox(
        slot_col,
        textvariable=gui.measurement_slot_var,
        values=tuple(str(slot) for slot in MEASUREMENT_SLOTS),
        width=7,
    ).pack(fill=tk.X)

    group_col = ttk.Frame(row, style="Card.TFrame")
    group_col.pack(side=tk.LEFT, fill=tk.X, expand=True)
    _field_label(group_col, "Group")
    group_combo = themed_combobox(
        group_col,
        textvariable=gui.measurement_group_var,
        values=tuple(MEASUREMENT_TYPES_BY_GROUP),
        width=16,
    )
    group_combo.pack(fill=tk.X)
    group_combo.bind("<<ComboboxSelected>>", gui._on_measurement_group_changed)

    row = ttk.Frame(body, style="Card.TFrame")
    row.pack(fill=tk.X, pady=(0, 8))
    _field_label(row, "Measurement type")
    measurement_type = themed_combobox(
        row,
        textvariable=gui.measurement_type_var,
        values=MEASUREMENT_TYPES_BY_GROUP[gui.measurement_group_var.get()],
        readonly=False,
    )
    measurement_type.pack(fill=tk.X)
    gui.measurement_type_combo = measurement_type
    measurement_type.bind(
        "<<ComboboxSelected>>",
        lambda _event: gui.measurement_type_var.set(gui.measurement_type_var.get().upper()),
    )

    row = ttk.Frame(body, style="Card.TFrame")
    row.pack(fill=tk.X, pady=(0, 8))

    src1_col = ttk.Frame(row, style="Card.TFrame")
    src1_col.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
    _field_label(src1_col, "Source 1")
    themed_combobox(
        src1_col,
        textvariable=gui.measurement_source1_var,
        values=MEASUREMENT_SOURCES,
    ).pack(fill=tk.X)

    src2_col = ttk.Frame(row, style="Card.TFrame")
    src2_col.pack(side=tk.LEFT, fill=tk.X, expand=True)
    _field_label(src2_col, "Source 2")
    themed_combobox(
        src2_col,
        textvariable=gui.measurement_source2_var,
        values=("",) + MEASUREMENT_SOURCES,
    ).pack(fill=tk.X)

    row = ttk.Frame(body, style="Card.TFrame")
    row.pack(fill=tk.X, pady=(2, 8))
    ttk.Button(
        row,
        text="Add / update measurement",
        style="Accent.TButton",
        command=gui.add_measurement_to_display,
    ).pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Button(row, text="Read value", command=gui.read_measurement_value).pack(
        side=tk.LEFT,
        fill=tk.X,
        expand=True,
        padx=(8, 0),
    )

    row = ttk.Frame(body, style="Card.TFrame")
    row.pack(fill=tk.X, pady=(0, 8))
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

    row = ttk.Frame(body, style="Card.TFrame")
    row.pack(fill=tk.X, pady=(0, 0))
    _field_label(row, "Last read value")
    ttk.Entry(row, textvariable=gui.measurement_value_var, state="readonly").pack(fill=tk.X)


def _field_label(parent: tk.Widget, text: str) -> None:
    ttk.Label(parent, text=text, style="Card.TLabel").pack(anchor="w", pady=(0, 2))


__all__ = [
    "MEASUREMENT_HELP_TEXT",
    "MEASUREMENT_TAB_TITLE",
    "build_measurement_tab",
]
