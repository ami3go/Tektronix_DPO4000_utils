"""Milestone-A production runtime shell for DPO4000 Desk v0.7.0.

This is the final compatibility layer above the historical feature-window MRO.
It keeps the v0.7 session/runtime remediation isolated from the v0.8 composition
rewrite while ensuring that the actually launched application obeys the async
scope contract end-to-end.
"""

from __future__ import annotations

import time
from threading import Event

from ..logger.models import LoggerMode, LoggerRecord, LoggerState
from ..logger.producer import capture_logger_record
from .automation_report_window import QtScopeWindow as AutomationReportQtScopeWindow
from .production_hardening_window import QtScopeWindow as ProductionHardenedQtScopeWindow

_BUS_CAPABILITY_DESCRIPTION = "Checking decoded BUS logger capability"


class QtScopeWindow(ProductionHardenedQtScopeWindow):
    """Launched v0.7 window with the complete Milestone-A runtime contract."""

    # ------------------------------------------------------------------
    # Shared asynchronous gateway completion hooks
    # ------------------------------------------------------------------
    def _run_action(
        self,
        description,
        callback,
        *,
        on_success=None,
        on_error=None,
        retain_session: bool = False,
    ):
        """Preserve health/retention/limits after async scope completion.

        Logger L13 predates the asynchronous gateway and historically measured a
        synchronous return value.  Calling the A12 async wrapper directly skips
        that obsolete override while preserving A12 reporting and A11 recovery.
        Logger health is then recorded at the real completion boundary.
        """

        # L11 still contains a legacy synchronous capability probe. Decoded BUS
        # extraction is deliberately unavailable until hardware qualification, so
        # fail this static gate without performing any GUI-thread scope I/O.
        if (
            str(description) == _BUS_CAPABILITY_DESCRIPTION
            and on_success is None
            and on_error is None
        ):
            return False

        started = time.monotonic()
        auto_before = int(self._automation_controller.statistics.succeeded)
        trigger_before = int(self._trigger_controller.statistics.succeeded)

        def completed(value: object) -> None:
            elapsed = max(0.0, time.monotonic() - started)
            if isinstance(value, LoggerRecord):
                self._logger_health.note_capture(value, elapsed)

            if on_success is not None:
                on_success(value)

            auto_after = int(self._automation_controller.statistics.succeeded)
            trigger_after = int(self._trigger_controller.statistics.succeeded)
            if trigger_after > trigger_before:
                self._register_completed_artifacts("trigger", trigger_after)
                self._check_run_limits()
            elif auto_after > auto_before:
                self._register_completed_artifacts("automation", auto_after)
                self._check_run_limits()

        def failed(exc: BaseException) -> None:
            if on_error is not None:
                on_error(exc)

        AutomationReportQtScopeWindow._run_action(
            self,
            description,
            callback,
            on_success=completed,
            on_error=failed,
            retain_session=retain_session,
        )
        return None

    # ------------------------------------------------------------------
    # A8/A9 guards for state machines overridden by production hardening
    # ------------------------------------------------------------------
    def _trigger_cycle(self) -> None:
        if self._check_run_limits() or not self._retention_pre_event_guard():
            return
        super()._trigger_cycle()

    def _trigger_bundle_cycle(self) -> None:
        if self._check_run_limits() or not self._retention_pre_event_guard():
            return
        super()._trigger_bundle_cycle()

    def _automation_burst_event(self) -> None:
        if self._check_run_limits() or not self._retention_pre_event_guard():
            return
        super()._automation_burst_event()

    # ------------------------------------------------------------------
    # L11 writer shutdown: bounded wait without a nested Qt event loop
    # ------------------------------------------------------------------
    def _wait_for_writer_stop(self, writer, timeout_s: float = 30.0) -> bool:
        """Wait for the disk writer with a hard bound and no nested QEventLoop."""

        return bool(writer.wait(max(0.1, float(timeout_s))))

    # ------------------------------------------------------------------
    # L11 bounded producer/writer capture path, asynchronous scope side
    # ------------------------------------------------------------------
    def _logger_tick(self) -> None:
        if self._logger_state is not LoggerState.RUNNING:
            return

        writer = self._logger_writer
        if writer is None:
            self._fail_buffered_logger("Logger writer is unavailable.")
            return
        snapshot = writer.snapshot()
        if snapshot.error:
            self._fail_buffered_logger(snapshot.error, writer_error=True)
            return
        if not writer.has_capacity():
            self._logger_statistics.skipped += 1
            self._append_log("Logger tick skipped: bounded writer queue is full")
            self._logger_refresh_status()
            return
        if self._logger_busy:
            self._logger_statistics.skipped += 1
            self._logger_refresh_status()
            return

        config = self._logger_config_active
        if config is None:
            return

        self._logger_busy = True
        self._logger_sequence += 1
        sequence = self._logger_sequence
        cancel = Event() if config.mode is LoggerMode.MIXED else None
        if cancel is not None:
            self._logger_capture_cancel = cancel
        before_transport = self._recovery_statistics.transport_failures
        description = (
            f"Logger synchronized capture #{sequence:08d}"
            if config.mode is LoggerMode.MIXED
            else f"Logger capture #{sequence:08d}"
        )

        def finalize() -> None:
            if cancel is not None:
                self._logger_capture_cancel = None
            self._logger_busy = False
            self._logger_refresh_status()

        def stopped_or_cancelled() -> bool:
            return bool(
                (cancel is not None and cancel.is_set())
                or self._logger_state not in {LoggerState.RUNNING, LoggerState.PAUSED}
            )

        def fail_runtime(error: BaseException) -> None:
            try:
                if stopped_or_cancelled():
                    self._logger_statistics.skipped += 1
                    return

                had_transport_failure = (
                    self._recovery_statistics.transport_failures > before_transport
                )
                if had_transport_failure:
                    self._logger_statistics.failed += 1
                    detail = (
                        self._recovery_statistics.last_error
                        or str(error)
                        or "transport failure"
                    )
                    self._logger_statistics.last_error = detail
                    policy = self._logger_recovery_policy()
                    consecutive = self._recovery_statistics.consecutive_failures
                    if consecutive >= policy.max_consecutive_failures:
                        self._fail_buffered_logger(
                            f"{consecutive} consecutive transport failures: {detail}",
                            count_failure=False,
                        )
                    else:
                        self._append_log(
                            "Logger record skipped after exhausted transport retries; "
                            f"consecutive failures {consecutive}/"
                            f"{policy.max_consecutive_failures}"
                        )
                    return

                self._fail_buffered_logger(str(error))
            finally:
                finalize()

        def captured(result: object) -> None:
            try:
                if stopped_or_cancelled():
                    self._logger_statistics.skipped += 1
                    return
                if not isinstance(result, LoggerRecord):
                    raise RuntimeError("Logger capture returned no record")

                self._logger_statistics.records_captured += 1
                accepted = writer.try_enqueue(result)
                if not accepted:
                    current = writer.snapshot()
                    if current.error:
                        self._fail_buffered_logger(current.error, writer_error=True)
                        return
                    self._logger_statistics.last_error = "Writer queue overflow"
                    if (
                        current.consecutive_overflows
                        >= writer.policy.stop_after_overflows
                    ):
                        self._fail_buffered_logger(
                            "Writer queue overflowed "
                            f"{current.consecutive_overflows} consecutive times."
                        )
                    else:
                        self._append_log(
                            "Logger record dropped because the bounded writer queue "
                            "could not accept it"
                        )
                    return

                self._logger_statistics.last_error = ""
                self.statusBar().showMessage(
                    f"Logger record {sequence} queued for disk"
                )
            except Exception as exc:  # noqa: BLE001 - fail closed on output errors.
                if stopped_or_cancelled():
                    self._logger_statistics.skipped += 1
                else:
                    self._fail_buffered_logger(str(exc))
            finally:
                finalize()

        self._run_action(
            description,
            lambda scope: capture_logger_record(
                scope,
                config,
                sequence,
                cancel_event=cancel,
            ),
            on_success=captured,
            on_error=fail_runtime,
            retain_session=True,
        )


__all__ = ["QtScopeWindow"]
