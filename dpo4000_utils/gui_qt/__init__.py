"""Experimental PySide6 GUI for Tektronix DPO4000 utilities.

This package is intentionally separate from ``dpo4000_utils.gui`` so the
existing Tkinter GUI remains stable while the Qt interface is tested.
"""

from __future__ import annotations

from .main_window import QtScopeWindow

__all__ = ["QtScopeWindow"]
