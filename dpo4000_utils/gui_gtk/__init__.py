"""Experimental GTK4 GUI for Tektronix DPO4000 utilities.

This package is intentionally separate from ``dpo4000_utils.gui`` so the
existing Tkinter GUI remains stable while the GTK4 interface is tested.
Importing this package does not import PyGObject until the GUI is launched.
"""

from __future__ import annotations

__all__ = ["GtkScopeWindow"]


def __getattr__(name: str):
    if name == "GtkScopeWindow":
        from .main_window import GtkScopeWindow

        return GtkScopeWindow
    raise AttributeError(name)
