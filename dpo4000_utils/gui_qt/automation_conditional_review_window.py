"""Reviewed A6 Conditional Capture UI behavior."""

from __future__ import annotations

from ..automation import AutomationState
from .automation_conditional_window import QtScopeWindow as AutomationA6QtScopeWindow


class QtScopeWindow(AutomationA6QtScopeWindow):
    """A6 window that ignores worker completions belonging to a stopped run."""

    def __init__(self, *args, **kwargs) -> None:
        self._discarded_conditional_completion = False
        super().__init__(*args, **kwargs)

    def _run_action(self, description, callback):
        tracked_generation = None
        if str(description).startswith("Evaluating conditional capture #"):
            tracked_generation = self._automation_controller.generation
        result = super()._run_action(description, callback)
        if (
            tracked_generation is not None
            and tracked_generation != self._automation_controller.generation
        ):
            self._discarded_conditional_completion = True
            return None
        return result

    def stop_automation(self) -> None:
        if (
            self._discarded_conditional_completion
            and self._automation_controller.state is AutomationState.IDLE
        ):
            self._discarded_conditional_completion = False
            self._automation_refresh_status()
            return
        self._discarded_conditional_completion = False
        super().stop_automation()


__all__ = ["QtScopeWindow"]
