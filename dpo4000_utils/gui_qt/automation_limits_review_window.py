"""Reviewed A8 run-limit lifecycle behavior."""

from __future__ import annotations

from .automation_limits_window import QtScopeWindow as AutomationA8QtScopeWindow


class QtScopeWindow(AutomationA8QtScopeWindow):
    """A8 window that retires its watchdog as soon as a run ends naturally."""

    def _start_run_limit_tracking_if_active(self, limits) -> None:
        super()._start_run_limit_tracking_if_active(limits)
        if limits.max_duration_s is None:
            watchdog = self._run_limit_watchdog
            if watchdog is not None:
                watchdog.stop()

    def _finalize_limit_tracking_if_inactive(self) -> None:
        if self._automation_any_active() or not self._run_limit_tracker.started:
            return
        watchdog = self._run_limit_watchdog
        if watchdog is not None:
            watchdog.stop()
        if not self._run_limit_stop_reason:
            self._run_limit_stop_reason = "Automation completed"
        self._automation_refresh_status()

    def _automation_tick(self) -> None:
        super()._automation_tick()
        self._finalize_limit_tracking_if_inactive()

    def _trigger_cycle(self) -> None:
        super()._trigger_cycle()
        self._finalize_limit_tracking_if_inactive()

    def _trigger_bundle_cycle(self) -> None:
        super()._trigger_bundle_cycle()
        self._finalize_limit_tracking_if_inactive()

    def _automation_burst_event(self) -> None:
        super()._automation_burst_event()
        self._finalize_limit_tracking_if_inactive()


__all__ = ["QtScopeWindow"]
