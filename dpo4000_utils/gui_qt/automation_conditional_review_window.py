"""Reviewed A6 Conditional Capture UI behavior."""

from __future__ import annotations

from .automation_conditional_window import QtScopeWindow as AutomationA6QtScopeWindow


class QtScopeWindow(AutomationA6QtScopeWindow):
    """A6 window that ignores worker completions belonging to a stopped run."""

    def _run_action(self, description, callback):
        tracked_generation = None
        if str(description).startswith("Evaluating conditional capture #"):
            tracked_generation = self._automation_controller.generation
        result = super()._run_action(description, callback)
        if (
            tracked_generation is not None
            and tracked_generation != self._automation_controller.generation
        ):
            return None
        return result


__all__ = ["QtScopeWindow"]
