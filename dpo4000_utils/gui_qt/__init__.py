"""PySide6 desktop application for Tektronix DPO4000 utilities."""

from __future__ import annotations

__all__ = ["QtScopeWindow"]


def __getattr__(name: str):
    if name == "QtScopeWindow":
        from .composition.window import QtScopeWindow

        return QtScopeWindow
    raise AttributeError(name)
