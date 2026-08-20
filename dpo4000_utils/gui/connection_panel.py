"""Connection tab builder for the Tkinter GUI.

The functions in this module build the Connection tab UI while delegating all
resource validation and hardware actions back to the active window object. This
keeps the visual layout separate from the monolithic main window without changing
runtime behavior.
"""

from __future__ import annotations

from typing import Any

import tkinter as tk
from tkinter import ttk

from ..connection import visaResourceAddr
from .style import themed_combobox, themed_radiobutton


CONNECTION_HINT_TEXT = "VXI-11: TCPIP0::<ip>::INSTR. Socket: TCPIP0::<ip>::4000::SOCKET."
ETHERNET_PROTOCOLS = ("VXI-11 / INSTR", "Raw SOCKET")
CONNECTION_MODE_LABELS = ("USB / VISA", "Ethernet")


def build_connection_card(window: Any, parent: tk.Widget) -> None:
    """Build the Connection tab contents for ``window``.

    ``window`` is expected to be a ScopeGui-compatible object that provides the
    Tk variables and command methods used by the existing main-window
    implementation. Keeping this as a free function avoids another deep subclass
    hierarchy for individual tab builders.
    """
    card = window._card(parent)
    card.pack(fill=tk.X, pady=(0, 10))
    window._section_title(card, "Connection")

    mode_row = ttk.Frame(card, style="Card.TFrame")
    mode_row.pack(fill=tk.X, padx=14, pady=(8, 6))
    ttk.Label(mode_row, text="Mode", style="Card.TLabel").pack(side=tk.LEFT, padx=(0, 10))
    themed_radiobutton(
        mode_row,
        text="USB / VISA",
        value="visa",
        variable=window.connection_mode_var,
        command=window._on_connection_mode_changed,
    ).pack(side=tk.LEFT, padx=(0, 10))
    themed_radiobutton(
        mode_row,
        text="Ethernet",
        value="ethernet",
        variable=window.connection_mode_var,
        command=window._on_connection_mode_changed,
    ).pack(side=tk.LEFT)

    visa_label_row = ttk.Frame(card, style="Card.TFrame")
    visa_label_row.pack(fill=tk.X, padx=14, pady=(6, 2))
    ttk.Label(visa_label_row, text="VISA resource", style="Card.TLabel").pack(side=tk.LEFT)

    visa_row = ttk.Frame(card, style="Card.TFrame")
    visa_row.pack(fill=tk.X, padx=14, pady=(0, 8))
    window.resource_combo = themed_combobox(
        visa_row,
        textvariable=window.resource_var,
        readonly=False,
        values=(visaResourceAddr,),
    )
    window.resource_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
    ttk.Button(visa_row, text="Refresh", command=window.list_visa_resources).pack(side=tk.LEFT)

    eth_box = ttk.Frame(card, style="Card.TFrame")
    eth_box.pack(fill=tk.X, padx=14, pady=(6, 8))

    eth_host_row = ttk.Frame(eth_box, style="Card.TFrame")
    eth_host_row.pack(fill=tk.X, pady=(0, 6))
    ttk.Label(eth_host_row, text="Ethernet IP/host", style="Card.TLabel").pack(side=tk.LEFT)
    ttk.Entry(eth_host_row, textvariable=window.eth_host_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

    eth_protocol_row = ttk.Frame(eth_box, style="Card.TFrame")
    eth_protocol_row.pack(fill=tk.X, pady=(0, 6))
    ttk.Label(eth_protocol_row, text="Protocol", style="Card.TLabel").pack(side=tk.LEFT)
    themed_combobox(
        eth_protocol_row,
        textvariable=window.eth_protocol_var,
        width=17,
        values=ETHERNET_PROTOCOLS,
    ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

    eth_port_row = ttk.Frame(eth_box, style="Card.TFrame")
    eth_port_row.pack(fill=tk.X, pady=(0, 6))
    ttk.Label(eth_port_row, text="Socket port", style="Card.TLabel").pack(side=tk.LEFT)
    ttk.Entry(eth_port_row, width=9, textvariable=window.eth_port_var).pack(side=tk.LEFT, padx=(8, 0))
    ttk.Button(eth_port_row, text="Use Ethernet resource", command=window.apply_ethernet_resource).pack(
        side=tk.LEFT, padx=(8, 0)
    )

    generated_label_row = ttk.Frame(card, style="Card.TFrame")
    generated_label_row.pack(fill=tk.X, padx=14, pady=(6, 2))
    ttk.Label(generated_label_row, text="Generated Ethernet resource", style="Card.TLabel").pack(side=tk.LEFT)

    generated_row = ttk.Frame(card, style="Card.TFrame")
    generated_row.pack(fill=tk.X, padx=14, pady=(0, 8))
    ttk.Entry(generated_row, textvariable=window.generated_resource_var, state="readonly").pack(
        side=tk.LEFT, fill=tk.X, expand=True
    )

    timeout_row = ttk.Frame(card, style="Card.TFrame")
    timeout_row.pack(fill=tk.X, padx=14, pady=(6, 8))
    ttk.Label(timeout_row, text="Timeout ms", style="Card.TLabel").pack(side=tk.LEFT)
    ttk.Entry(timeout_row, width=9, textvariable=window.timeout_var).pack(side=tk.LEFT, padx=(8, 0))

    button_row = ttk.Frame(card, style="Card.TFrame")
    button_row.pack(fill=tk.X, padx=14, pady=(0, 14))
    ttk.Button(button_row, text="Test IDN", style="Accent.TButton", command=window.test_connection).pack(
        side=tk.LEFT, fill=tk.X, expand=True
    )

    ttk.Label(
        card,
        text=CONNECTION_HINT_TEXT,
        style="Muted.TLabel",
        wraplength=360,
        justify=tk.LEFT,
    ).pack(fill=tk.X, padx=14, pady=(0, 14))


__all__ = ["CONNECTION_HINT_TEXT", "CONNECTION_MODE_LABELS", "ETHERNET_PROTOCOLS", "build_connection_card"]
