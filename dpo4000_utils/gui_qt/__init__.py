"""Experimental PySide6 GUI for Tektronix DPO4000 utilities.

This package is intentionally separate from ``dpo4000_utils.gui`` so the
existing Tkinter GUI remains stable while the Qt interface is tested.
"""

from __future__ import annotations

__all__ = ["QtScopeWindow"]


def __getattr__(name: str):
    """Load Qt classes lazily so importing the package does not require PySide6."""
    if name == "QtScopeWindow":
        from .enhanced_window import QtScopeWindow

        return QtScopeWindow
    raise AttributeError(name)
