"""Reviewed A1 Automation window behavior.

This thin layer keeps the implementation commit reviewable while tightening the
A1 control-state policy before later automation backlog items build on it.
"""

from __future__ import annotations

from ..automation import AutomationState
from .automation_window import QtScopeWindow as AutomationA1QtScopeWindow


class QtScopeWindow(AutomationA1QtScopeWindow):
    """A1 window with reviewed Run-once enablement semantics."""

    def _automation_refresh_status(self) -> None:
        super()._automation_refresh_status()
        controller = getattr(self, "_automation_controller", None)
        run_once = getattr(self, "automation_run_once_button", None)
        if controller is None or run_once is None:
            return
        active = controller.state in {AutomationState.RUNNING, AutomationState.PAUSED}
        operation_active = bool(getattr(self, "_operation_active", False))
        connection_ok = bool(getattr(self, "_connection_ok", False))
        run_once.setEnabled(not active and not operation_active and connection_ok)


__all__ = ["QtScopeWindow"]
