"""PySide6 desktop application for Tektronix DPO4000 utilities."""

from __future__ import annotations

__all__ = ["QtScopeWindow"]


def __getattr__(name: str):
    """Load Qt classes lazily so importing the driver package does not require PySide6."""
    if name == "QtScopeWindow":
        # Previous launched layer retained in history: from .automation_burst_window import QtScopeWindow
        from .automation_limits_review_window import QtScopeWindow

        return QtScopeWindow
    raise AttributeError(name)
