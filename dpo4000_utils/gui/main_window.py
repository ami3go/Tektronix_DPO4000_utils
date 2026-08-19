"""Compatibility shim for the former monolithic GUI module.

The historical base window implementation moved to ``base_window.py``. New code
should import ``dpo4000_utils.gui.scope_gui.ScopeGui`` or
``dpo4000_utils.gui.app.ScopeGui``. This module remains to preserve older imports
that used ``dpo4000_utils.gui.main_window.ScopeGui``.
"""

from __future__ import annotations

from .base_window import DEFAULT_RESTORE_TIMEOUT_MS, ScopeGui

__all__ = ["DEFAULT_RESTORE_TIMEOUT_MS", "ScopeGui"]
