"""Production-hardening overrides for the final DPO4000 Desk window.

The legacy feature layers predate the v0.7 asynchronous scope gateway and several
of them consumed ``_run_action()`` return values synchronously.  The final window
is the migration boundary: every production Automation A1..A7 and Logger capture
state machine below finishes its token/record only from the asynchronous completion
callback.  This keeps mature UI/layout code intact while making the launched path
fully non-blocking.
"""

from __future__ import annotations

import time
from pathlib import Path
from threading import Event

from PySide6.QtCore import QTimer

from ..automation import (
    AutomationState,
    BurstEventResult,
    ConditionalPollResult,
    MeasurementLogResult,
    TimedWaveformResult,
    TriggerBundleResult,
    acquire_trigger_bundle,
    append_measurement_row,
    run_burst_event,
    run_conditional_poll,
    save_full_record_csv,
)
from ..automation.triggered import TriggerWaitResult, wait_for_fresh_single
from ..logger.models import LoggerMode, LoggerRecord, LoggerState
from ..logger.producer import capture_logger_record
from ..logger.retention import LoggerRetentionError
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

    # ------------------------------------------------------------------
    # Automation A1: periodic image
    # ------------------------------------------------------------------
    def _automation_capture_image(self, *, force: bool) -> None:
        controller = self._automation_controller
        token = controller.begin_event(force=force)
        if token is None:
            self._automation_refresh_status()
            return
        try:
            path = self._automation_build_png_path(token.sequence)
            path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001 - output validation failure.
            controller.finish_event(token, success=False, error=str(exc))
            self._append_log(f"Automation output error: {exc}")
            self._automation_refresh_status()
            return

        def completed(result: object) -> None:
            if token.generation != controller.generation:
                return
            if isinstance(result, str) and result:
                saved_path = Path(result)
                accepted = controller.finish_event(token, success=True)
                self._automation_last_path = saved_path
                if accepted:
                    self._last_image_path = saved_path
                    self.statusBar().showMessage(
                        f"Automation image saved: {saved_path.name}"
                    )
            else:
                controller.finish_event(token, success=False, error="Capture returned no path")
            self._automation_refresh_status()

        def failed(exc: BaseException) -> None:
            if token.generation == controller.generation:
                controller.finish_event(token, success=False, error=str(exc))
                self._automation_refresh_status()

        self._run_action(
            f"Automation image #{token.sequence:04d}",
            lambda scope: str(scope.save_image_path(path)),
            on_success=completed,
            on_error=failed,
        )

    # ------------------------------------------------------------------
    # Automation A2: fresh Single -> image
    # ------------------------------------------------------------------
    def _trigger_cycle(self) -> None:
        trigger = self._trigger_controller
        if trigger.state is not AutomationState.RUNNING:
            return
        config = trigger.config
        if config is None:
            trigger.stop()
            self._automation_refresh_status()
            return
        token = trigger.begin_cycle()
        if token is None:
            self._automation_refresh_status()
            return

        cancel = Event()
        self._trigger_cancel_event = cancel
        self._trigger_last_state = "ARMED"
        self._automation_refresh_status()

        def failed(exc: BaseException) -> None:
            self._trigger_cancel_event = None
            if token.generation != trigger.generation:
                return
            if trigger.state is AutomationState.RUNNING:
                trigger.finish_cycle(token, success=False, error=str(exc))
                trigger.stop()
            self._automation_refresh_status()

        def waited(result: object) -> None:
            self._trigger_cancel_event = None
            if token.generation != trigger.generation:
                return
            if trigger.state is not AutomationState.RUNNING:
                trigger.cancel_cycle(token)
                self._automation_refresh_status()
                return
            if not isinstance(result, TriggerWaitResult):
                trigger.finish_cycle(
                    token,
                    success=False,
                    error="Could not read acquisition completion state",
                )
                trigger.stop()
                self._automation_refresh_status()
                return

            self._trigger_last_state = result.trigger_state or self._trigger_last_state
            if result.cancelled:
                trigger.cancel_cycle(token)
                self._automation_refresh_status()
                return
            if not result.completed:
                error = result.error or "Single acquisition did not complete"
                trigger.finish_cycle(token, success=False, error=error)
                trigger.stop()
                self._automation_refresh_status()
                return
            self._save_triggered_image(token)

        self._run_action(
            f"Waiting for triggered acquisition #{token.sequence:04d}",
            lambda scope: self._wait_for_triggered_single(
                scope,
                cancel,
                poll_interval_s=config.poll_interval_s,
            ),
            on_success=waited,
            on_error=failed,
            retain_session=True,
        )

    def _save_triggered_image(self, token) -> None:
        trigger = self._trigger_controller
        try:
            path = self._automation_build_png_path(token.sequence)
            path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001 - file validation failure.
            trigger.finish_cycle(token, success=False, error=str(exc))
            trigger.stop()
            self._automation_refresh_status()
            return

        def failed(exc: BaseException) -> None:
            if token.generation != trigger.generation:
                return
            trigger.finish_cycle(token, success=False, error=str(exc))
            trigger.stop()
            self._automation_refresh_status()

        def saved(result: object) -> None:
            if token.generation != trigger.generation:
                return
            if trigger.state is not AutomationState.RUNNING:
                trigger.cancel_cycle(token)
                self._automation_refresh_status()
                return
            if not isinstance(result, str) or not result:
                failed(RuntimeError("Triggered image save returned no path"))
                return

            saved_path = Path(result)
            if trigger.finish_cycle(token, success=True):
                self._automation_last_path = saved_path
                self._last_image_path = saved_path
                self.statusBar().showMessage(f"Triggered image saved: {saved_path.name}")

            config = trigger.config
            if trigger.state is AutomationState.RUNNING and config is not None and config.rearm:
                QTimer.singleShot(0, self._trigger_cycle)
            else:
                trigger.stop()
            self._automation_refresh_status()

        self._run_action(
            f"Saving triggered image #{token.sequence:04d}",
            lambda scope: str(scope.save_image_path(path)),
            on_success=saved,
            on_error=failed,
        )

    # ------------------------------------------------------------------
    # Automation A3: fresh Single -> image + CSV evidence bundle
    # ------------------------------------------------------------------
    def _trigger_bundle_cycle(self) -> None:
        trigger = self._trigger_controller
        if trigger.state is not AutomationState.RUNNING:
            return
        config = trigger.config
        if config is None:
            trigger.stop()
            self._automation_refresh_status()
            return
        token = trigger.begin_cycle()
        if token is None:
            self._automation_refresh_status()
            return

        try:
            image_path, csv_path = self._automation_build_bundle_paths(token.sequence)
            image_path.parent.mkdir(parents=True, exist_ok=True)
            csv_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001 - file validation failure.
            trigger.finish_cycle(token, success=False, error=str(exc))
            trigger.stop()
            self._append_log(f"Automation A3 output error: {exc}")
            self._automation_refresh_status()
            return

        cancel = Event()
        self._trigger_cancel_event = cancel
        self._trigger_last_state = "ARMED"
        self._automation_refresh_status()

        def partial_detail(result: TriggerBundleResult | None = None) -> str:
            partial: list[str] = []
            if result is not None:
                if result.image_path is not None:
                    partial.append(Path(result.image_path).name)
                if result.csv_path is not None:
                    partial.append(Path(result.csv_path).name)
            else:
                if image_path.exists():
                    partial.append(image_path.name)
                if csv_path.exists():
                    partial.append(csv_path.name)
            return f"; partial artifacts: {', '.join(partial)}" if partial else ""

        def failed(exc: BaseException) -> None:
            self._trigger_cancel_event = None
            if token.generation != trigger.generation:
                return
            detail = partial_detail()
            trigger.finish_cycle(token, success=False, error=f"{exc}{detail}")
            trigger.stop()
            self._append_log(f"Automation A3 failed: {exc}{detail}")
            self._automation_refresh_status()

        def captured(result: object) -> None:
            self._trigger_cancel_event = None
            if token.generation != trigger.generation:
                return
            if trigger.state is not AutomationState.RUNNING:
                trigger.cancel_cycle(token)
                self._automation_refresh_status()
                return
            if not isinstance(result, TriggerBundleResult):
                failed(RuntimeError("Image + CSV capture returned no bundle result"))
                return

            self._trigger_last_state = result.trigger_state or self._trigger_last_state
            if result.cancelled:
                trigger.cancel_cycle(token)
                self._automation_refresh_status()
                return
            if not result.completed or not result.artifacts_complete:
                detail = partial_detail(result)
                error = result.error or "Single acquisition bundle did not complete"
                trigger.finish_cycle(token, success=False, error=f"{error}{detail}")
                trigger.stop()
                self._append_log(f"Automation A3 failed: {error}{detail}")
                self._automation_refresh_status()
                return

            if trigger.finish_cycle(token, success=True):
                self._automation_last_path = Path(result.image_path)
                self._automation_last_csv_path = Path(result.csv_path)
                self._last_image_path = Path(result.image_path)
                self._append_log(
                    f"A3 bundle #{token.sequence:04d}: {Path(result.image_path).name}, "
                    f"{Path(result.csv_path).name}, {result.point_count} points"
                )
                self.statusBar().showMessage(
                    f"Triggered image + CSV saved: #{token.sequence:04d} "
                    f"({result.point_count} points)"
                )

            if trigger.state is AutomationState.RUNNING and config.rearm:
                QTimer.singleShot(0, self._trigger_bundle_cycle)
            else:
                trigger.stop()
            self._automation_refresh_status()

        self._run_action(
            f"Capturing triggered image + CSV #{token.sequence:04d}",
            lambda scope: acquire_trigger_bundle(
                scope,
                cancel,
                poll_interval_s=config.poll_interval_s,
                image_path=image_path,
                csv_path=csv_path,
            ),
            on_success=captured,
            on_error=failed,
            retain_session=True,
        )

    # ------------------------------------------------------------------
    # Automation A4: timed waveform CSV
    # ------------------------------------------------------------------
    def _automation_capture_csv(self, *, force: bool) -> None:
        controller = self._automation_controller
        token = controller.begin_event(force=force)
        if token is None:
            self._automation_refresh_status()
            return
        try:
            path = self._automation_build_csv_path(token.sequence)
            path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001 - output validation failure.
            controller.finish_event(token, success=False, error=str(exc))
            self._append_log(f"Automation A4 output error: {exc}")
            self._stop_timed_waveform_after_failure()
            return

        def fail(error: str) -> None:
            if token.generation != controller.generation:
                return
            controller.finish_event(token, success=False, error=error)
            self._append_log(f"Automation A4 failed: {error}")
            self._stop_timed_waveform_after_failure()

        def completed(result: object) -> None:
            if token.generation != controller.generation:
                return
            if not isinstance(result, TimedWaveformResult) or not result.success:
                error = result.error if isinstance(result, TimedWaveformResult) else "Waveform CSV capture failed"
                fail(error or "Waveform CSV capture failed")
                return
            accepted = controller.finish_event(token, success=True)
            if accepted and result.csv_path is not None:
                saved_path = Path(result.csv_path)
                self._automation_last_csv_path = saved_path
                self._automation_last_path = saved_path
                self.statusBar().showMessage(
                    f"Automation waveform CSV saved: {saved_path.name} "
                    f"({result.point_count} points)"
                )
            self._automation_refresh_status()

        self._run_action(
            f"Automation waveform CSV #{token.sequence:04d}",
            lambda scope: save_full_record_csv(scope, path),
            on_success=completed,
            on_error=lambda exc: fail(str(exc)),
        )

    # ------------------------------------------------------------------
    # Automation A5: measurement logger
    # ------------------------------------------------------------------
    def _automation_capture_measurements(self, *, force: bool) -> None:
        controller = self._automation_controller
        token = controller.begin_event(force=force)
        if token is None:
            self._automation_refresh_status()
            return
        path = self._measurement_log_path
        started = self._measurement_run_started_utc
        slots = self._measurement_slots_active
        if path is None or started is None or not slots:
            controller.finish_event(
                token,
                success=False,
                error="Measurement logger run state is incomplete.",
            )
            self._stop_measurement_logger_after_failure()
            return

        def fail(error: str) -> None:
            if token.generation != controller.generation:
                return
            controller.finish_event(token, success=False, error=error)
            self._append_log(f"Automation A5 failed: {error}")
            self._stop_measurement_logger_after_failure()

        def completed(result: object) -> None:
            if token.generation != controller.generation:
                return
            if not isinstance(result, MeasurementLogResult) or not result.success:
                error = result.error if isinstance(result, MeasurementLogResult) else "Measurement logging failed"
                fail(error or "Measurement logging failed")
                return
            accepted = controller.finish_event(token, success=True)
            if accepted and result.csv_path is not None:
                saved_path = Path(result.csv_path)
                self._automation_last_path = saved_path
                self._automation_last_csv_path = saved_path
                if result.slot_errors:
                    detail = ", ".join(
                        f"MEAS{slot}: {error}" for slot, error in result.slot_errors.items()
                    )
                    self._append_log(
                        f"Measurement logger row has unavailable values: {detail}"
                    )
                self.statusBar().showMessage(
                    f"Measurement row appended: {saved_path.name} (row {token.sequence})"
                )
            self._automation_refresh_status()

        self._run_action(
            f"Logging measurement row #{token.sequence:04d}",
            lambda scope: append_measurement_row(
                scope,
                path,
                slots,
                run_started_utc=started,
            ),
            on_success=completed,
            on_error=lambda exc: fail(str(exc)),
        )

    # ------------------------------------------------------------------
    # Automation A6: conditional capture
    # ------------------------------------------------------------------
    def _automation_capture_condition(self, *, force: bool) -> None:
        controller = self._automation_controller
        token = controller.begin_event(force=force)
        if token is None:
            self._automation_refresh_status()
            return
        evaluator = self._conditional_evaluator
        if evaluator is None:
            controller.finish_event(
                token,
                success=False,
                error="Conditional evaluator is unavailable.",
            )
            self._automation_refresh_status()
            return
        action = self._conditional_action_active
        try:
            image_path, csv_path = self._build_conditional_paths(token.sequence, action)
            for path in (image_path, csv_path):
                if path is not None:
                    path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001 - output validation failure.
            controller.finish_event(token, success=False, error=str(exc))
            self._append_log(f"Automation A6 output error: {exc}")
            self.stop_automation()
            return

        def fail(error: str) -> None:
            if token.generation != controller.generation:
                return
            controller.finish_event(token, success=False, error=error)
            self._append_log(f"Automation A6 failed: {error}")
            self.stop_automation()

        def completed(result: object) -> None:
            if token.generation != controller.generation:
                return
            if not isinstance(result, ConditionalPollResult):
                fail("Conditional capture returned no poll result")
                return

            evaluation = result.evaluation
            self._conditional_last_value = evaluation.value
            if not evaluation.valid:
                self._conditional_last_state = f"Invalid: {evaluation.error}"
                controller.finish_skipped(token, reason=evaluation.error)
                self._automation_refresh_status()
                return
            if not evaluation.fire:
                self._conditional_last_state = (
                    f"Matched; debounce/cooldown pending ({evaluation.streak})"
                    if evaluation.matched
                    else "No match"
                )
                controller.finish_skipped(token)
                self._automation_refresh_status()
                return

            artifacts = result.artifacts
            if artifacts is None or not artifacts.success:
                error = artifacts.error if artifacts is not None else "Conditional artifacts were not saved"
                self._conditional_last_state = f"Capture failed: {error}"
                fail(error)
                return

            self._conditional_last_state = "Captured"
            if controller.finish_event(token, success=True):
                if artifacts.image_path is not None:
                    self._automation_last_path = Path(artifacts.image_path)
                    self._last_image_path = Path(artifacts.image_path)
                if artifacts.csv_path is not None:
                    self._automation_last_csv_path = Path(artifacts.csv_path)
                    if artifacts.image_path is None:
                        self._automation_last_path = Path(artifacts.csv_path)
                self._append_log(
                    f"A6 capture #{token.sequence:04d}: value {evaluation.value:g}, {action.value}"
                )
                self.statusBar().showMessage(
                    f"Conditional capture saved: #{token.sequence:04d} "
                    f"({evaluation.value:g})"
                )
            self._automation_refresh_status()

        self._run_action(
            f"Evaluating conditional capture #{token.sequence:04d}",
            lambda scope: run_conditional_poll(
                scope,
                evaluator,
                now_s=time.monotonic(),
                action=action,
                image_path=str(image_path) if image_path is not None else None,
                csv_path=str(csv_path) if csv_path is not None else None,
            ),
            on_success=completed,
            on_error=lambda exc: fail(str(exc)),
        )

    # ------------------------------------------------------------------
    # Automation A7: finite burst
    # ------------------------------------------------------------------
    def _automation_burst_event(self) -> None:
        timer = self._automation_timer
        if timer is not None:
            timer.stop()
        controller = self._automation_controller
        config = self._burst_config_active
        if controller.state is not AutomationState.RUNNING or config is None:
            return
        if controller.statistics.succeeded >= config.count:
            self._finish_burst_complete()
            return

        token = controller.begin_event()
        if token is None:
            self._automation_refresh_status()
            return
        try:
            image_path, csv_path = self._build_burst_paths(token.sequence, config.action)
            for path in (image_path, csv_path):
                if path is not None:
                    path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001 - output validation failure.
            controller.finish_event(token, success=False, error=str(exc))
            self._stop_burst_after_failure(f"Burst output error: {exc}")
            return

        cancel = Event()
        self._burst_cancel_event = cancel
        self._burst_last_state = (
            "Waiting for Single" if config.single_acquisition else "Saving artifacts"
        )
        self._automation_refresh_status()

        def fail(error: str) -> None:
            self._burst_cancel_event = None
            if token.generation != controller.generation:
                return
            controller.finish_event(token, success=False, error=error)
            self._stop_burst_after_failure(error)

        def completed(result: object) -> None:
            self._burst_cancel_event = None
            if token.generation != controller.generation:
                return
            if not isinstance(result, BurstEventResult):
                fail("Burst event returned no result")
                return
            if result.cancelled:
                controller.finish_skipped(token, reason="Burst event cancelled")
                self._burst_last_state = (
                    "Paused" if controller.state is AutomationState.PAUSED else "Cancelled"
                )
                self._automation_refresh_status()
                return

            artifacts = result.artifacts
            if artifacts is None or not artifacts.success:
                error = artifacts.error if artifacts is not None else "Burst artifacts were not saved"
                fail(error)
                return
            accepted = controller.finish_event(token, success=True)
            if not accepted:
                return
            if artifacts.image_path is not None:
                self._automation_last_path = Path(artifacts.image_path)
                self._last_image_path = Path(artifacts.image_path)
            if artifacts.csv_path is not None:
                self._automation_last_csv_path = Path(artifacts.csv_path)
                if artifacts.image_path is None:
                    self._automation_last_path = Path(artifacts.csv_path)

            successes = controller.statistics.succeeded
            self._burst_last_state = "Captured"
            self._append_log(
                f"A7 burst event {successes}/{config.count}: {config.action.value}"
            )
            self.statusBar().showMessage(
                f"Burst capture {successes}/{config.count} complete"
            )
            if successes >= config.count:
                self._finish_burst_complete()
            elif controller.state is AutomationState.RUNNING:
                self._schedule_next_burst()
            self._automation_refresh_status()

        self._run_action(
            f"Burst capture #{token.sequence:04d}",
            lambda scope: run_burst_event(
                scope,
                cancel,
                config,
                image_path=str(image_path) if image_path is not None else None,
                csv_path=str(csv_path) if csv_path is not None else None,
            ),
            on_success=completed,
            on_error=lambda exc: fail(str(exc)),
            retain_session=config.single_acquisition,
        )

    # ------------------------------------------------------------------
    # Logger final capture path (all modes, including MIXED)
    # ------------------------------------------------------------------
    def _logger_tick(self) -> None:
        if self._logger_state is not LoggerState.RUNNING:
            return
        if self._logger_busy:
            self._logger_statistics.skipped += 1
            self._logger_refresh_status()
            return

        config = self._logger_config_active
        output = self._logger_output_session
        if config is None or output is None:
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
                    detail = self._recovery_statistics.last_error or str(error) or "transport failure"
                    self._logger_statistics.last_error = detail
                    policy = self._logger_recovery_policy()
                    consecutive = self._recovery_statistics.consecutive_failures
                    if consecutive >= policy.max_consecutive_failures:
                        self._fail_logger_runtime(
                            f"{consecutive} consecutive transport failures: {detail}",
                            output,
                            count_failure=False,
                            retain_closed_segments=True,
                        )
                    else:
                        self._append_log(
                            "Logger record skipped after exhausted transport retries; "
                            f"consecutive failures {consecutive}/{policy.max_consecutive_failures}"
                        )
                    return
                self._fail_logger_runtime(str(error), output)
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
                output.append(result)
                self._logger_statistics.records_written = output.records_written
                self._logger_statistics.bytes_written = output.bytes_written
                self._logger_statistics.last_error = ""
                self._logger_last_file = output.current_paths[-1] if output.current_paths else None
                if result.metadata.get("partial"):
                    self._append_log(
                        f"Logger record {sequence} written as PARTIAL: {result.metadata}"
                    )
                if output.rotation_count > self._logger_retention_last_rotation:
                    self._apply_completed_logger_segments(output)
                self.statusBar().showMessage(f"Logger record {sequence} written")
            except LoggerRetentionError as exc:
                self._fail_logger_runtime(f"Retention failure: {exc}", output)
            except Exception as exc:  # noqa: BLE001 - capture/output failures fail closed.
                if stopped_or_cancelled():
                    self._logger_statistics.skipped += 1
                else:
                    self._fail_logger_runtime(str(exc), output)
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
