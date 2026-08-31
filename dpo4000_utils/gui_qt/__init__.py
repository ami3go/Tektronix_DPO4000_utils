"""PySide6 desktop application for Tektronix DPO4000 utilities."""

from __future__ import annotations

__all__ = ["QtScopeWindow"]


def __getattr__(name: str):
    """Load Qt classes lazily so importing the driver package does not require PySide6."""
    if name == "QtScopeWindow":
        from .ui_polish_window import QtScopeWindow

        return QtScopeWindow
    raise AttributeError(name)
