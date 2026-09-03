"""Reviewed Logger L14 report lifecycle hardening."""

from __future__ import annotations

from ..logger.reporting import LoggerRunReporter
from .logger_health_window import QtScopeWindow as LoggerL13QtScopeWindow
from .logger_report_window import QtScopeWindow as LoggerL14QtScopeWindow


class QtScopeWindow(LoggerL14QtScopeWindow):
    """Harden L14 so report-event failures stop logging but never block final JSON."""

    def _safe_logger_report_event(
        self,
        event_type: str,
        *,
        details: dict | None = None,
        sequence: int | None = None,
        fail_logger_on_error: bool = True,
    ) -> None:
        reporter = self._logger_reporter
        if reporter is None or reporter.finalized or self._logger_report_failed:
            return
        try:
            reporter.append_event(event_type, details=details, sequence=sequence)
        except Exception as exc:  # noqa: BLE001 - report failure is a terminal run condition.
            self._logger_report_failed = True
            self._logger_report_stop_reason = "report_failure"
            message = f"Logger report event write failed: {exc}"
            self._append_log(message)
            if fail_logger_on_error and (
                self._logger_active() or self._logger_writer_active()
            ):
                LoggerL13QtScopeWindow._fail_buffered_logger(self, message)

    def _fail_buffered_logger(
        self,
        message: str,
        *,
        count_failure: bool = True,
        writer_error: bool = False,
    ) -> None:
        self._logger_report_stop_reason = "logger_failure"
        self._safe_logger_report_event(
            "ERROR",
            sequence=self._logger_sequence or None,
            details={"message": str(message), "writer_error": bool(writer_error)},
            fail_logger_on_error=False,
        )
        LoggerL13QtScopeWindow._fail_buffered_logger(
            self,
            message,
            count_failure=count_failure,
            writer_error=writer_error,
        )
        self._checkpoint_logger_report(reason="failure", force=True)

    def _finalize_logger_report(self, *, reason: str | None = None) -> None:
        reporter: LoggerRunReporter | None = self._logger_reporter
        if reporter is None or reporter.finalized or self._logger_writer_active():
            return
        stop_reason = reason or self._logger_report_stop_reason or "stopped"
        state = self._logger_report_state()
        final_error = str(state.get("last_error", "") or "")

        if not self._logger_report_failed:
            try:
                reporter.append_event(
                    "RUN_END",
                    sequence=self._logger_sequence or None,
                    details={
                        "stop_reason": stop_reason,
                        "records_written": state["records"]["written"],
                        "records_dropped": state["records"]["dropped"],
                        "records_reconciled": state["reconciliation"]["records_reconciled"],
                        "final_error": final_error,
                    },
                )
            except Exception as exc:  # noqa: BLE001 - final JSON remains authoritative.
                self._logger_report_failed = True
                self._append_log(f"Logger RUN_END event write failed: {exc}")

        try:
            self._logger_report_path = reporter.finalize(
                stop_reason=stop_reason,
                state=state,
                final_error=final_error,
            )
            self._append_log(f"Logger run report finalized: {self._logger_report_path}")
        except Exception as exc:  # noqa: BLE001 - shutdown must continue if disk is unavailable.
            self._logger_report_failed = True
            self._append_log(f"Logger report finalization failed: {exc}")


__all__ = ["QtScopeWindow"]
