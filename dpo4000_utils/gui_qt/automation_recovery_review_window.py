"""Reviewed A11 recovery accounting and run scoping."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

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

    def _run_action(
        self,
        description: str,
        callback: Callable[[Any], object],
        *,
        on_success: Callable[[object], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        retain_session: bool = False,
    ) -> None:
        """Preserve manual-action recovery history at async completion time.

        This review layer originally wrapped a synchronous ``_run_action`` return
        value. The production gateway is asynchronous now, so all accounting must
        happen from completion callbacks while transparently forwarding the async
        gateway keywords used by A12 reporting and the composed GUI shell.
        """
        replay_safe = self._recovery_replay_safe(description)
        before_failures = self._recovery_statistics.consecutive_failures
        before_error = self._recovery_statistics.last_error

        def completed(value: object) -> None:
            # A successful manual/non-replay-safe action must not erase an
            # Automation transport-failure streak established by A11.
            if (
                not replay_safe
                and bool(getattr(self, "_connection_ok", False))
                and before_failures
            ):
                self._recovery_statistics.consecutive_failures = before_failures
                self._recovery_statistics.last_error = before_error
                self._automation_refresh_status()
            if on_success is not None:
                on_success(value)

        super()._run_action(
            description,
            callback,
            on_success=completed,
            on_error=on_error,
            retain_session=retain_session,
        )


__all__ = ["QtScopeWindow"]
