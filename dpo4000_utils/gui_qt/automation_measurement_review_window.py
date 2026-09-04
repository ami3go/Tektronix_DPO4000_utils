"""Reviewed A5 Measurement Logger UI behavior."""

from __future__ import annotations

from ..automation import AutomationState
from .automation_measurement_window import QtScopeWindow as AutomationA5QtScopeWindow


class QtScopeWindow(AutomationA5QtScopeWindow):
    """A5 window with configuration controls locked during in-flight one-shot work."""

    def _automation_refresh_status(self) -> None:
        super()._automation_refresh_status()
        periodic_active = self._automation_controller.state in {
            AutomationState.RUNNING,
            AutomationState.PAUSED,
        }
        trigger_active = self._trigger_controller.state in {
            AutomationState.RUNNING,
            AutomationState.PAUSED,
        }
        operation_active = bool(getattr(self, "_operation_active", False))
        editable = not periodic_active and not trigger_active and not operation_active
        for checkbox in getattr(self, "automation_measurement_slots", {}).values():
            checkbox.setEnabled(editable)


__all__ = ["QtScopeWindow"]
