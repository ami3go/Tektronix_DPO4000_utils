"""Logger L10 bounded automatic reconnect using the existing A11 action gateway."""

from __future__ import annotations

from threading import Event

from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QFormLayout, QLabel, QSpinBox

from ..automation.recovery import RecoveryPolicy, RecoveryStatistics
from ..logger.models import LoggerMode, LoggerRecord, LoggerState
from ..logger.producer import capture_logger_record
from ..logger.retention import LoggerRetentionError
from .logger_retention_window import QtScopeWindow as LoggerL9QtScopeWindow

_LOGGER_REPLAY_SAFE_PREFIXES = (
    "Logger capture #",
    "Logger synchronized capture #",
)


class QtScopeWindow(LoggerL9QtScopeWindow):
    """L9 Logger extended with transport reconnect/retry and stale-stop guards."""

    def __init__(self, *args, **kwargs) -> None:
        self._logger_starting = False
        super().__init__(*args, **kwargs)

    def _build_logger_acquisition_card(self):
        card = super()._build_logger_acquisition_card()
        form = card.layout()
        if not isinstance(form, QFormLayout):
            return card

        self.logger_reconnect_enabled = QCheckBox("Automatic reconnect")
        self.logger_reconnect_enabled.setChecked(True)
        self.logger_reconnect_retries = QSpinBox()
        self.logger_reconnect_retries.setRange(0, 20)
        self.logger_reconnect_retries.setValue(2)
        self.logger_reconnect_delay = QDoubleSpinBox()
        self.logger_reconnect_delay.setRange(0.1, 300.0)
        self.logger_reconnect_delay.setDecimals(1)
        self.logger_reconnect_delay.setValue(1.0)
        self.logger_reconnect_delay.setSuffix(" s")
        self.logger_reconnect_max_failures = QSpinBox()
        self.logger_reconnect_max_failures.setRange(1, 1000)
        self.logger_reconnect_max_failures.setValue(5)

        form.addRow(self.logger_reconnect_enabled)
        form.addRow("Retries per record", self.logger_reconnect_retries)
        form.addRow("Retry base delay", self.logger_reconnect_delay)
        form.addRow("Stop after transport failures", self.logger_reconnect_max_failures)
        return card

    def _build_logger_health_card(self):
        card = super()._build_logger_health_card()
        form = card.layout()
        if isinstance(form, QFormLayout):
            self.logger_retry_label = QLabel("0")
            self.logger_reconnect_label = QLabel("0")
            self.logger_transport_failure_label = QLabel("0")
            form.addRow("Retry attempts", self.logger_retry_label)
            form.addRow("Reconnects", self.logger_reconnect_label)
            form.addRow("Transport failures", self.logger_transport_failure_label)
        return card

    def _logger_recovery_policy(self) -> RecoveryPolicy:
        return RecoveryPolicy(
            enabled=self.logger_reconnect_enabled.isChecked(),
            max_retries=int(self.logger_reconnect_retries.value()),
            retry_delay_s=float(self.logger_reconnect_delay.value()),
            max_consecutive_failures=int(self.logger_reconnect_max_failures.value()),
        )

    def _selected_recovery_policy(self) -> RecoveryPolicy:
        if self._logger_starting or self._logger_active():
            return self._logger_recovery_policy()
        return super()._selected_recovery_policy()

    def _recovery_replay_safe(self, description: str) -> bool:
        if any(str(description).startswith(prefix) for prefix in _LOGGER_REPLAY_SAFE_PREFIXES):
            return True
        return super()._recovery_replay_safe(description)

    def start_logger(self) -> None:
        if self._logger_active():
            return
        self._recovery_statistics = RecoveryStatistics()
        self._logger_starting = True
        try:
            super().start_logger()
        finally:
            self._logger_starting = False
        self._logger_refresh_status()

    def _finish_scope_action_error(self, description: str, exc: BaseException) -> None:
        if not (self._logger_starting or self._logger_active()):
            return super()._finish_scope_action_error(description, exc)
        self._connection_ok = False
        self._last_action = f"Failed: {description}"
        self.statusBar().showMessage(f"Logger transport failure: {exc}")
        self._append_log(f"LOGGER TRANSPORT ERROR: {exc}")
        self._operation_active = False
        self._update_scope_control_enabled()
        self._update_status_strip()
        return None

    def _fail_logger_runtime(self, message: str, output) -> None:
        self._logger_statistics.failed += 1
        self._logger_statistics.last_error = str(message)
        timer = self._logger_timer
        if timer is not None:
            timer.stop()
        try:
            output.close()
        except Exception as close_exc:  # noqa: BLE001
            self._append_log(f"Logger output close after failure also failed: {close_exc}")
        self._logger_output_session = None
        self._logger_state = LoggerState.FAILED
        self._append_log(f"Logger failed: {message}")
        self.statusBar().showMessage("Logger failed")

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
        try:
            description = (
                f"Logger synchronized capture #{sequence:08d}"
                if config.mode is LoggerMode.MIXED
                else f"Logger capture #{sequence:08d}"
            )
            result = self._run_action(
                description,
                lambda scope: capture_logger_record(
                    scope,
                    config,
                    sequence,
                    cancel_event=cancel,
                ),
            )

            # Stop may close output while the worker is still returning. Pause may
            # finish the current record, but Stop/Failed must never append stale data.
            if (cancel is not None and cancel.is_set()) or self._logger_state not in {
                LoggerState.RUNNING,
                LoggerState.PAUSED,
            }:
                self._logger_statistics.skipped += 1
                return

            if not isinstance(result, LoggerRecord):
                had_transport_failure = (
                    self._recovery_statistics.transport_failures > before_transport
                )
                if had_transport_failure:
                    self._logger_statistics.failed += 1
                    error = self._recovery_statistics.last_error or "transport failure"
                    self._logger_statistics.last_error = error
                    policy = self._logger_recovery_policy()
                    consecutive = self._recovery_statistics.consecutive_failures
                    if consecutive >= policy.max_consecutive_failures:
                        self._fail_logger_runtime(
                            f"{consecutive} consecutive transport failures: {error}",
                            output,
                        )
                    else:
                        self._append_log(
                            "Logger record skipped after exhausted transport retries; "
                            f"consecutive failures {consecutive}/{policy.max_consecutive_failures}"
                        )
                    return
                raise RuntimeError(
                    str(getattr(self, "_last_action", "Logger capture failed"))
                )

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
        except Exception as exc:  # noqa: BLE001 - non-transport failures fail immediately.
            if (cancel is not None and cancel.is_set()) or self._logger_state not in {
                LoggerState.RUNNING,
                LoggerState.PAUSED,
            }:
                self._logger_statistics.skipped += 1
                return
            self._fail_logger_runtime(str(exc), output)
        finally:
            if cancel is not None:
                self._logger_capture_cancel = None
            self._logger_busy = False
            self._logger_refresh_status()

    def _logger_refresh_status(self) -> None:
        super()._logger_refresh_status()
        stats = self._recovery_statistics
        for name, value in (
            ("logger_retry_label", stats.retry_attempts),
            ("logger_reconnect_label", stats.reconnects),
            ("logger_transport_failure_label", stats.transport_failures),
        ):
            label = getattr(self, name, None)
            if label is not None:
                label.setText(str(value))

        editable = not self._logger_active() and not bool(
            getattr(self, "_operation_active", False)
        )
        for name in (
            "logger_reconnect_enabled",
            "logger_reconnect_retries",
            "logger_reconnect_delay",
            "logger_reconnect_max_failures",
        ):
            control = getattr(self, name, None)
            if control is not None:
                control.setEnabled(editable)


__all__ = ["QtScopeWindow"]
