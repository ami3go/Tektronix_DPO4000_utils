"""Reviewed A11 recovery accounting and run scoping."""

from __future__ import annotations

from ..automation.recovery import RecoveryStatistics
from .automation_recovery_window import QtScopeWindow as AutomationA11QtScopeWindow


class QtScopeWindow(AutomationA11QtScopeWindow):
    """A11 window with recovery statistics scoped to Automation activity."""

    def _reset_recovery_run_statistics(self) -> None:
        self._recovery_statistics = RecoveryStatistics()
        self._automation_refresh_status()

    def start_automation(self) -> None:
        if not self._automation_any_active():
            self._reset_recovery_run_statistics()
        super().start_automation()

    def run_automation_once(self) -> None:
        if not self._automation_any_active():
            self._reset_recovery_run_statistics()
        super().run_automation_once()

    def _run_action(self, description, callback):
        replay_safe = self._recovery_replay_safe(description)
        before_failures = self._recovery_statistics.consecutive_failures
        before_error = self._recovery_statistics.last_error
        result = super()._run_action(description, callback)
        # A successful manual/non-replay-safe action must not erase an Automation failure streak.
        if not replay_safe and bool(getattr(self, "_connection_ok", False)) and before_failures:
            self._recovery_statistics.consecutive_failures = before_failures
            self._recovery_statistics.last_error = before_error
            self._automation_refresh_status()
        return result


__all__ = ["QtScopeWindow"]
