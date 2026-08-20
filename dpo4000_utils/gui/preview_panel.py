"""Screen preview and image/CSV action panel builder."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .style import themed_combobox

PREVIEW_TITLE = "Screen preview"
PREVIEW_EMPTY_TEXT = "Press 'Capture preview' to read the current scope screen."
PREVIEW_COPY_HINT = "After capture, press Ctrl+C while the preview is focused to copy the image."
POST_IMAGE_TRIGGER_VALUES = ("", "1", "2", "3", "4")


def build_image_preview(gui, parent: tk.Widget) -> None:
    """Build the left-side screen preview card and bottom action bar."""
    card = gui._card(parent)
    card.grid(row=0, column=0, sticky="nsew")

    # _section_title() uses pack() inside this card, so all children of the same
    # card must also use pack(). Tkinter does not allow mixing pack() and grid()
    # in one parent container.
    gui._section_title(card, PREVIEW_TITLE)

    gui.preview_label = ttk.Label(
        card,
        text=PREVIEW_EMPTY_TEXT,
        style="Card.TLabel",
        anchor="center",
        takefocus=True,
    )
    gui.preview_label.pack(fill=tk.BOTH, expand=True, padx=14, pady=(8, 4))
    gui.preview_label.bind("<Configure>", gui._on_preview_resize)
    gui.preview_label.bind("<Button-1>", lambda event: event.widget.focus_set())
    gui.preview_label.bind("<Control-c>", gui.copy_preview_to_clipboard)
    gui.preview_label.bind("<Control-C>", gui.copy_preview_to_clipboard)

    ttk.Label(
        card,
        text=PREVIEW_COPY_HINT,
        style="Muted.TLabel",
        anchor="center",
    ).pack(fill=tk.X, padx=14, pady=(0, 8))

    build_preview_bottom_actions(gui, card)


def build_preview_bottom_actions(gui, parent: tk.Widget) -> None:
    """Build Image/CSV controls directly below the screen preview."""
    action_bar = ttk.Frame(parent, style="Card.TFrame")
    action_bar.pack(fill=tk.X, padx=14, pady=(0, 14))

    options_row = ttk.Frame(action_bar, style="Card.TFrame")
    options_row.pack(fill=tk.X, pady=(0, 8))

    ttk.Checkbutton(
        options_row,
        text="Re-arm trigger after image capture",
        variable=gui.rearm_after_image_var,
    ).pack(side=tk.LEFT)

    ttk.Label(options_row, text="Trigger channel", style="Card.TLabel").pack(side=tk.LEFT, padx=(18, 8))
    themed_combobox(
        options_row,
        textvariable=gui.trigger_channel_var,
        width=7,
        values=POST_IMAGE_TRIGGER_VALUES,
    ).pack(side=tk.LEFT)

    buttons_row = ttk.Frame(action_bar, style="Card.TFrame")
    buttons_row.pack(fill=tk.X)

    ttk.Button(buttons_row, text="Capture preview", command=gui.capture_preview).pack(
        side=tk.LEFT,
        fill=tk.X,
        expand=True,
    )
    ttk.Button(buttons_row, text="Copy preview", command=gui.copy_preview_to_clipboard).pack(
        side=tk.LEFT,
        fill=tk.X,
        expand=True,
        padx=(8, 0),
    )
    ttk.Button(buttons_row, text="Save PNG image...", command=gui.save_png_image).pack(
        side=tk.LEFT,
        fill=tk.X,
        expand=True,
        padx=(8, 0),
    )
    ttk.Button(
        buttons_row,
        text="Save enabled channels to CSV...",
        style="Accent.TButton",
        command=gui.save_csv,
    ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))


__all__ = [
    "POST_IMAGE_TRIGGER_VALUES",
    "PREVIEW_COPY_HINT",
    "PREVIEW_EMPTY_TEXT",
    "PREVIEW_TITLE",
    "build_image_preview",
    "build_preview_bottom_actions",
]
