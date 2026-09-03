"""Logger L11 bounded producer/writer pipeline."""

from __future__ import annotations

import time
from pathlib import Path
from threading import Event

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QFormLayout, QLabel, QSpinBox

from ..automation.recovery import RecoveryStatistics
from ..logger.buffering import BufferPolicy, BufferSnapshot, LoggerWriterWorker
from ..logger.models import LoggerMode, LoggerRecord, LoggerState, LoggerStatistics
from ..logger.output import LoggerOutputSession
from ..logger.producer import capture_logger_record
from ..logger.retention import LoggerRetentionManager
from .logger_page_layout import FILE_PAGE_INDEX
from .logger_recovery_window import QtScopeWindow as LoggerL10QtScopeWindow


class QtScopeWindow(LoggerL10QtScopeWindow):
    """L10 Logger with scope production decoupled from bounded disk writing."""

    def __init__(self, *args, **kwargs) -> None:
        self._logger_writer: LoggerWriterWorker | None = None
        self._logger_writer_monitor: QTimer | None = None
        self._logger_last_writer_snapshot = BufferSnapshot()
        self._logger_writer_error_announced = False
        super().__init__(*args, **kwargs)
        self._logger_writer_monitor = QTimer(self)
        self._logger_writer_monitor.setInterval(250)
        self._logger_writer_monitor.timeout.connect(self._logger_writer_monitor_tick)

    def _build_logger_acquisition_card(self):
        card = super()._build_logger_acquisition_card()
        form = card.layout()
        if not isinstance(form, QFormLayout):
            return card

        self.logger_queue_records = QSpinBox()
        self.logger_queue_records.setRange(1, 1024)
        self.logger_queue_records.setValue(8)
        self.logger_queue_memory_mb = QSpinBox()
        self.logger_queue_memory_mb.setRange(1, 16_384)
        self.logger_queue_memory_mb.setValue(256)
        self.logger_queue_memory_mb.setSuffix(" MB")
        self.logger_queue_stop_overflows = QSpinBox()
        self.logger_queue_stop_overflows.setRange(1, 10_000)
        self.logger_queue_stop_overflows.setValue(5)
        form.addRow("Writer queue records", self.logger_queue_records)
        form.addRow("Writer queue memory", self.logger_queue_memory_mb)
        form.addRow("Stop after queue overflows", self.logger_queue_stop_overflows)
        return card

    def _build_logger_health_card(self):
        card = super()._build_logger_health_card()
        form = card.layout()
        if isinstance(form, QFormLayout):
            self.logger_queue_depth_label = QLabel("0 / 0")
            self.logger_queue_memory_label = QLabel("0.0 MB")
            self.logger_queue_peak_label = QLabel("0")
            self.logger_dropped_label = QLabel("0")
            self.logger_writer_time_label = QLabel("0.000 s")
            self.logger_writer_error_label = QLabel("--")
            self.logger_writer_error_label.setWordWrap(True)
            form.addRow("Queue depth", self.logger_queue_depth_label)
            form.addRow("Queued memory", self.logger_queue_memory_label)
            form.addRow("Queue peak", self.logger_queue_peak_label)
            form.addRow("Dropped records", self.logger_dropped_label)
            form.addRow("Last disk write", self.logger_writer_time_label)
            form.addRow("Writer error", self.logger_writer_error_label)
        return card

    def _selected_buffer_policy(self) -> BufferPolicy:
        return BufferPolicy(
            max_records=int(self.logger_queue_records.value()),
            max_bytes=int(self.logger_queue_memory_mb.value()) * 1024 * 1024,
            stop_after_overflows=int(self.logger_queue_stop_overflows.value()),
        )

    def _logger_writer_active(self) -> bool:
        writer = self._logger_writer
        return writer is not None and writer.is_alive

    def _logger_output_factory(self, config, root: Path, output_format, rotation_policy):
        metadata = {
            "mode": config.mode.value,
            "waveform_sources": list(config.waveform_sources),
            "measurement_slots": list(config.measurement_slots),
            "bus_slots": list(config.bus_slots),
            "encoding": config.encoding,
            "sample_width": config.sample_width,
        }

        def factory() -> LoggerOutputSession:
            return LoggerOutputSession(
                root,
                output_format,
                mode=config.mode,
                measurement_slots=config.measurement_slots,
                run_metadata=metadata,
                rotation_policy=rotation_policy,
            )

        return factory

    @staticmethod
    def _logger_retention_callbacks(manager: LoggerRetentionManager):
        state = {"rotation_count": 0}

        def after_write(output: LoggerOutputSession) -> None:
            if output.rotation_count <= state["rotation_count"]:
                return
            manager.register_closed_segments(output.completed_segments)
            manager.apply()
            state["rotation_count"] = output.rotation_count

        def after_close(output: LoggerOutputSession) -> None:
            manager.register_closed_segments(output.completed_segments)
            manager.apply()
            state["rotation_count"] = output.rotation_count

        return after_write, after_close

    def start_logger(self) -> None:
        if self._logger_active() or self._logger_writer_active():
            return
        if self._automation_any_active():
            self._message("Logger", "Stop Automation before starting Logger.", error=True)
            return
        if not bool(getattr(self, "_connection_ok", False)):
            self._message("Logger", "Test the scope connection before starting Logger.", error=True)
            return

        writer: LoggerWriterWorker | None = None
        retention_manager: LoggerRetentionManager | None = None
        self._logger_starting = True
        self._recovery_statistics = RecoveryStatistics()
        try:
            self._ensure_control_page_built(FILE_PAGE_INDEX)
            config = self._logger_config()
            root = self._logger_root()
            output_format = self._selected_output_format()
            rotation_policy = self._selected_rotation_policy()
            buffer_policy = self._selected_buffer_policy()
            retention_manager = LoggerRetentionManager(
                root,
                self._selected_logger_retention_policy(),
            )
            retention_manager.apply()

            if config.bus_slots:
                supported = self._run_action(
                    "Checking decoded BUS logger capability",
                    lambda scope: bool(scope.supports_decoded_bus_events()),
                )
                if supported is not True:
                    raise RuntimeError(
                        "Decoded BUS extraction is not hardware-qualified for this driver/scope."
                    )

            after_write, after_close = self._logger_retention_callbacks(retention_manager)
            writer = LoggerWriterWorker(
                self._logger_output_factory(
                    config,
                    root,
                    output_format,
                    rotation_policy,
                ),
                buffer_policy,
                after_write=after_write,
                after_close=after_close,
            )
            writer.start()
        except Exception as exc:  # noqa: BLE001 - start must be atomic/fail closed.
            if writer is not None and writer.is_alive:
                writer.request_stop(drain=False)
                self._logger_writer = writer
                self._logger_state = LoggerState.FAILED
                monitor = self._logger_writer_monitor
                if monitor is not None:
                    monitor.start()
            self._message("Logger", f"Could not start Logger: {exc}", error=True)
            return
        finally:
            self._logger_starting = False

        assert retention_manager is not None
        assert writer is not None
        self._logger_retention_manager = retention_manager
        self._logger_writer = writer
        self._logger_last_writer_snapshot = writer.snapshot()
        self._logger_writer_error_announced = False
        self._logger_output_session = None
        self._logger_config_active = config
        self._logger_state = LoggerState.RUNNING
        self._logger_statistics = LoggerStatistics(started_monotonic=time.monotonic())
        self._logger_sequence = 0
        self._logger_last_file = None

        timer = self._logger_timer
        if timer is None:
            writer.request_stop(drain=False)
            self._logger_state = LoggerState.FAILED
            self._logger_refresh_status()
            return
        timer.setInterval(max(1, int(round(config.interval_s * 1000.0))))
        timer.start()
        monitor = self._logger_writer_monitor
        if monitor is not None:
            monitor.start()
        self._append_log(
            "Logger L11 started: bounded queue "
            f"{buffer_policy.max_records} records / "
            f"{buffer_policy.max_bytes / (1024 * 1024):.0f} MB"
        )
        self.statusBar().showMessage("Logger running with bounded background writer")
        self._logger_refresh_status()
        QTimer.singleShot(0, self._logger_tick)

    def _writer_snapshot(self) -> BufferSnapshot:
        writer = self._logger_writer
        if writer is not None:
            self._logger_last_writer_snapshot = writer.snapshot()
        return self._logger_last_writer_snapshot

    def _logger_writer_monitor_tick(self) -> None:
        writer = self._logger_writer
        if writer is None:
            monitor = self._logger_writer_monitor
            if monitor is not None:
                monitor.stop()
            return

        snapshot = writer.snapshot()
        self._logger_last_writer_snapshot = snapshot
        self._logger_statistics.records_written = snapshot.written_records
        self._logger_statistics.bytes_written = snapshot.bytes_written
        if snapshot.output_paths:
            self._logger_last_file = Path(snapshot.output_paths[-1])

        if snapshot.error and not self._logger_writer_error_announced:
            self._logger_writer_error_announced = True
            self._logger_statistics.failed += 1
            self._logger_statistics.last_error = snapshot.error
            self._logger_state = LoggerState.FAILED
            timer = self._logger_timer
            if timer is not None:
                timer.stop()
            self._append_log(f"Logger writer failed: {snapshot.error}")
            self.statusBar().showMessage("Logger writer failed")
            writer.request_stop(drain=False)

        if snapshot.stopped:
            monitor = self._logger_writer_monitor
            if monitor is not None:
                monitor.stop()
            self._logger_writer = None

        self._logger_refresh_status()

    def _wait_for_writer_stop(
        self,
        writer: LoggerWriterWorker,
        timeout_s: float = 30.0,
    ) -> bool:
        if writer.wait(0):
            return True
        loop = QEventLoop(self)
        poll = QTimer(self)
        poll.setInterval(50)
        deadline = time.monotonic() + max(0.1, float(timeout_s))

        def check() -> None:
            if writer.wait(0) or time.monotonic() >= deadline:
                poll.stop()
                loop.quit()

        poll.timeout.connect(check)
        poll.start()
        loop.exec()
        poll.deleteLater()
        return writer.wait(0)

    def stop_logger(self) -> None:
        timer = self._logger_timer
        if timer is not None:
            timer.stop()
        cancel = getattr(self, "_logger_capture_cancel", None)
        if cancel is not None:
            cancel.set()

        writer = self._logger_writer
        was_active = self._logger_active() or self._logger_writer_active()
        self._logger_state = LoggerState.IDLE
        self._logger_config_active = None
        if writer is not None:
            writer.request_stop(drain=True)
            stopped = self._wait_for_writer_stop(writer)
            snapshot = writer.snapshot()
            self._logger_last_writer_snapshot = snapshot
            self._logger_statistics.records_written = snapshot.written_records
            self._logger_statistics.bytes_written = snapshot.bytes_written
            if not stopped:
                writer.request_stop(drain=False)
                self._logger_state = LoggerState.FAILED
                self._logger_statistics.failed += 1
                self._logger_statistics.last_error = (
                    "Writer did not drain within the shutdown safety timeout."
                )
                self._append_log(self._logger_statistics.last_error)
            elif snapshot.error:
                self._logger_state = LoggerState.FAILED
                if not self._logger_writer_error_announced:
                    self._logger_writer_error_announced = True
                    self._logger_statistics.failed += 1
                self._logger_statistics.last_error = snapshot.error
            else:
                self._logger_writer = None

        if was_active:
            self._append_log(
                "Logger stopped"
                if self._logger_state is LoggerState.IDLE
                else "Logger stopped with error"
            )
            self.statusBar().showMessage(
                "Logger stopped"
                if self._logger_state is LoggerState.IDLE
                else "Logger failed during stop"
            )
        self._logger_refresh_status()

    def _fail_buffered_logger(
        self,
        message: str,
        *,
        count_failure: bool = True,
        writer_error: bool = False,
    ) -> None:
        if writer_error:
            if self._logger_writer_error_announced:
                count_failure = False
            else:
                self._logger_writer_error_announced = True
        if count_failure:
            self._logger_statistics.failed += 1
        self._logger_statistics.last_error = str(message)
        self._logger_state = LoggerState.FAILED
        timer = self._logger_timer
        if timer is not None:
            timer.stop()
        writer = self._logger_writer
        if writer is not None:
            writer.request_stop(drain=True)
        self._append_log(f"Logger failed: {message}")
        self.statusBar().showMessage("Logger failed")

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
                        self._fail_buffered_logger(
                            f"{consecutive} consecutive transport failures: {error}",
                            count_failure=False,
                        )
                    return
                raise RuntimeError(
                    str(getattr(self, "_last_action", "Logger capture failed"))
                )

            self._logger_statistics.records_captured += 1
            accepted = writer.try_enqueue(result)
            if not accepted:
                snapshot = writer.snapshot()
                if snapshot.error:
                    self._fail_buffered_logger(snapshot.error, writer_error=True)
                    return
                self._logger_statistics.last_error = "Writer queue overflow"
                if snapshot.consecutive_overflows >= writer.policy.stop_after_overflows:
                    self._fail_buffered_logger(
                        f"Writer queue overflowed {snapshot.consecutive_overflows} consecutive times."
                    )
                else:
                    self._append_log(
                        "Logger record dropped because the bounded writer queue could not accept it"
                    )
                return
            self._logger_statistics.last_error = ""
            self.statusBar().showMessage(f"Logger record {sequence} queued for disk")
        except Exception as exc:  # noqa: BLE001 - non-transport capture errors fail closed.
            if (cancel is not None and cancel.is_set()) or self._logger_state not in {
                LoggerState.RUNNING,
                LoggerState.PAUSED,
            }:
                self._logger_statistics.skipped += 1
                return
            self._fail_buffered_logger(str(exc))
        finally:
            if cancel is not None:
                self._logger_capture_cancel = None
            self._logger_busy = False
            self._logger_refresh_status()

    def _logger_refresh_status(self) -> None:
        super()._logger_refresh_status()
        snapshot = self._writer_snapshot()
        policy = self._logger_writer.policy if self._logger_writer is not None else None

        queue_depth = getattr(self, "logger_queue_depth_label", None)
        queue_memory = getattr(self, "logger_queue_memory_label", None)
        queue_peak = getattr(self, "logger_queue_peak_label", None)
        dropped = getattr(self, "logger_dropped_label", None)
        write_time = getattr(self, "logger_writer_time_label", None)
        writer_error = getattr(self, "logger_writer_error_label", None)
        if queue_depth is not None:
            max_records = policy.max_records if policy is not None else 0
            queue_depth.setText(f"{snapshot.queued_records} / {max_records}")
        if queue_memory is not None:
            queue_memory.setText(f"{snapshot.queued_bytes / (1024 * 1024):.1f} MB")
        if queue_peak is not None:
            queue_peak.setText(str(snapshot.peak_records))
        if dropped is not None:
            dropped.setText(str(snapshot.dropped_records))
        if write_time is not None:
            write_time.setText(f"{snapshot.last_write_s:.3f} s")
        if writer_error is not None:
            writer_error.setText(snapshot.error or "--")

        for label_name, value in (
            ("logger_segment_label", snapshot.segment_index),
            ("logger_rotation_count_label", snapshot.rotation_count),
        ):
            label = getattr(self, label_name, None)
            if label is not None:
                label.setText(str(value))
        self._logger_statistics.records_written = snapshot.written_records
        self._logger_statistics.bytes_written = snapshot.bytes_written
        if snapshot.output_paths:
            self._logger_last_file = Path(snapshot.output_paths[-1])

        editable = (
            not self._logger_active()
            and not self._logger_writer_active()
            and not bool(getattr(self, "_operation_active", False))
        )
        for name in (
            "logger_queue_records",
            "logger_queue_memory_mb",
            "logger_queue_stop_overflows",
        ):
            control = getattr(self, name, None)
            if control is not None:
                control.setEnabled(editable)
        start_button = getattr(self, "logger_start_button", None)
        if start_button is not None and self._logger_writer_active():
            start_button.setEnabled(False)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name.
        self.stop_logger()
        super().closeEvent(event)


__all__ = ["QtScopeWindow"]
