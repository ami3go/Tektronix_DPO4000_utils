"""Reviewed A12 report finalization ordering."""

from __future__ import annotations

from .automation_report_window import QtScopeWindow as AutomationA12QtScopeWindow


class QtScopeWindow(AutomationA12QtScopeWindow):
    """A12 window that never finalizes a Run-once report while I/O is still pending."""

    def __init__(self, *args, **kwargs) -> None:
        self._automation_report_run_once_dispatch = False
        super().__init__(*args, **kwargs)

    def _finalize_automation_report(self, stop_reason: str) -> None:
        if self._automation_report_run_once_dispatch or self._automation_report_in_action:
            return
        super()._finalize_automation_report(stop_reason)

    def run_automation_once(self) -> None:
        self._automation_report_run_once_dispatch = True
        try:
            super().run_automation_once()
        finally:
            self._automation_report_run_once_dispatch = False
        if self._automation_any_active():
            watchdog = self._automation_report_watchdog
            if watchdog is not None:
                watchdog.start()
        elif not self._automation_report_in_action:
            self._finalize_automation_report("run_once_complete")


__all__ = ["QtScopeWindow"]
