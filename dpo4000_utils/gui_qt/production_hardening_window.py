"""Production-hardening overrides for the final DPO4000 Desk window."""

from __future__ import annotations

from threading import Event

from ..automation.triggered import TriggerWaitResult, wait_for_fresh_single
from .logger_report_review_window import QtScopeWindow as LoggerReportReviewedQtScopeWindow


class QtScopeWindow(LoggerReportReviewedQtScopeWindow):
    """Final window with cross-cutting production safety hardening."""

    @staticmethod
    def _wait_for_triggered_single(
        scope,
        cancel: Event,
        *,
        poll_interval_s: float,
    ) -> TriggerWaitResult:
        """Use the shared fresh-Single state machine for A2 trigger capture."""

        return wait_for_fresh_single(
            scope,
            cancel,
            poll_interval_s=poll_interval_s,
            timeout_s=30.0,
        )


__all__ = ["QtScopeWindow"]
