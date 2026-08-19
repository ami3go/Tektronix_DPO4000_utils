"""Settings tab builder for output paths, naming, and setup files."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

SETTINGS_TITLE = "Output and scope settings"
FILENAME_FORMAT_HINT = "Filename format: <prefix><base><_timestamp optional>.<extension>"
NAMING_SECTIONS = ("PNG images", "CSV waveforms", "Settings JSON")


def build_settings_card(gui, parent: tk.Widget) -> None:
    """Build the Settings tab contents."""
    card = gui._card(parent)
    card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
    gui._section_title(card, SETTINGS_TITLE)

    body = ttk.Frame(card, style="Card.TFrame")
    body.pack(fill=tk.BOTH, expand=True, padx=14, pady=(8, 14))

    folder_row = ttk.Frame(body, style="Card.TFrame")
    folder_row.pack(fill=tk.X, pady=(0, 10))
    ttk.Label(folder_row, text="Destination folder", style="Card.TLabel").pack(anchor="w")

    folder_pick_row = ttk.Frame(body, style="Card.TFrame")
    folder_pick_row.pack(fill=tk.X, pady=(0, 12))
    ttk.Entry(folder_pick_row, textvariable=gui.output_folder_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Button(folder_pick_row, text="Pick folder", command=gui.pick_output_folder).pack(side=tk.LEFT, padx=(8, 0))

    ttk.Label(
        body,
        text=FILENAME_FORMAT_HINT,
        style="Muted.TLabel",
        wraplength=360,
        justify=tk.LEFT,
    ).pack(fill=tk.X, pady=(0, 10))

    build_naming_row(
        body,
        title="PNG images",
        prefix_var=gui.png_prefix_var,
        base_var=gui.png_base_var,
        timestamp_var=gui.png_add_timestamp_var,
    )
    build_naming_row(
        body,
        title="CSV waveforms",
        prefix_var=gui.csv_prefix_var,
        base_var=gui.csv_base_var,
        timestamp_var=gui.csv_add_timestamp_var,
    )
    build_naming_row(
        body,
        title="Settings JSON",
        prefix_var=gui.settings_prefix_var,
        base_var=gui.settings_base_var,
        timestamp_var=gui.settings_add_timestamp_var,
    )

    ttk.Separator(body).pack(fill=tk.X, pady=(8, 10))

    ttk.Checkbutton(
        body,
        text="Wait for *OPC? after restore (can timeout on DPO4000)",
        variable=gui.restore_wait_opc_var,
    ).pack(anchor="w", pady=(0, 8))

    ttk.Button(body, text="Save settings JSON", command=gui.save_settings).pack(fill=tk.X, pady=3)
    ttk.Button(body, text="Restore settings JSON...", style="Accent.TButton", command=gui.restore_settings).pack(
        fill=tk.X,
        pady=3,
    )


def build_naming_row(
    parent: tk.Widget,
    title: str,
    prefix_var: tk.StringVar,
    base_var: tk.StringVar,
    timestamp_var: tk.BooleanVar,
) -> None:
    """Build one compact filename-options row in the Settings tab."""
    box = ttk.Frame(parent, style="Card.TFrame")
    box.pack(fill=tk.X, pady=(0, 10))

    ttk.Label(box, text=title, style="Card.TLabel").pack(anchor="w", pady=(0, 4))

    row = ttk.Frame(box, style="Card.TFrame")
    row.pack(fill=tk.X)

    ttk.Label(row, text="Prefix", style="Card.TLabel").pack(side=tk.LEFT)
    ttk.Entry(row, width=9, textvariable=prefix_var).pack(side=tk.LEFT, padx=(6, 10))

    ttk.Label(row, text="Base", style="Card.TLabel").pack(side=tk.LEFT)
    ttk.Entry(row, width=13, textvariable=base_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 10))

    ttk.Checkbutton(row, text="Timestamp", variable=timestamp_var).pack(side=tk.LEFT)


__all__ = [
    "FILENAME_FORMAT_HINT",
    "NAMING_SECTIONS",
    "SETTINGS_TITLE",
    "build_naming_row",
    "build_settings_card",
]
