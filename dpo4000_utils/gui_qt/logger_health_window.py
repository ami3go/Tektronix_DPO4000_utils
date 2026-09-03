"""Logger L13 runtime health and throughput telemetry."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from PySide6.QtWidgets import QFormLayout, QLabel, QProgressBar

from ..logger.health import LoggerHealthAccumulator, compute_logger_health
from ..logger.models import LoggerRecord, LoggerState
from .logger_profiles_window import QtScopeWindow as LoggerL12QtScopeWindow


class QtScopeWindow(LoggerL12QtScopeWindow):
    """L12 Logger extended with sustained-run health telemetry."""

    def __init__(self, *args, **kwargs) -> None:
        self._logger_health = LoggerHealthAccumulator()
        self._logger_health_started_monotonic: float | None = None
        self._logger_health_ended_monotonic: float | None = None
        super().__init__(*args, **kwargs)

    def _build_logger_health_card(self):
        card = super()._build_logger_health_card()
        form = card.layout()
        if not isinstance(form, QFormLayout):
            return card

        self.logger_health_elapsed_label = QLabel("0.0 s")
        self.logger_health_captured_label = QLabel("0")
        self.logger_health_capture_rate_label = QLabel("0.000 records/s")
        self.logger_health_points_rate_label = QLabel("0 points/s")
        self.logger_health_scope_payload_label = QLabel("0.000 MB/s")
        self.logger_health_disk_rate_label = QLabel("0.000 MB/s")
        self.logger_health_writer_duty_label = QLabel("0.0 %")
        self.logger_health_scope_time_label = QLabel("0.000 s")
        self.logger_health_queue_pressure = QProgressBar()
        self.logger_health_queue_pressure.setRange(0, 1000)
        self.logger_health_queue_pressure.setValue(0)
        self.logger_health_queue_pressure.setFormat("0.0 %")
        self.logger_health_queue_peak_memory_label = QLabel("0.0 MB")
        self.logger_health_segment_bytes_label = QLabel("0.0 MB")
        self.logger_health_total_bytes_label = QLabel("0.0 MB")
        self.logger_health_measurement_rows_label = QLabel("0")
        self.logger_health_bus_events_label = QLabel("0")
        self.logger_health_last_record_label = QLabel("--")
        self.logger_health_last_record_status_label = QLabel("--")
        self.logger_health_last_record_utc_label = QLabel("--")
        self.logger_health_last_record_utc_label.setWordWrap(True)
        self.logger_health_writer_state_label = QLabel("--")
        self.logger_health_resource_label = QLabel("--")
        self.logger_health_resource_label.setWordWrap(True)
        self.logger_health_idn_label = QLabel("--")
        self.logger_health_idn_label.setWordWrap(True)
        self.logger_health_session_label = QLabel("--")
        self.logger_health_recovery_label = QLabel("0 reconnects / 0 retries")
        self.logger_health_last_error_label = QLabel("--")
        self.logger_health_last_error_label.setWordWrap(True)
        self.logger_health_disk_runway_label = QLabel("--")

        form.addRow("Elapsed", self.logger_health_elapsed_label)
        form.addRow("Captured records", self.logger_health_captured_label)
        form.addRow("Capture rate", self.logger_health_capture_rate_label)
        form.addRow("Waveform throughput", self.logger_health_points_rate_label)
        form.addRow("Scope waveform payload", self.logger_health_scope_payload_label)
        form.addRow("Disk throughput", self.logger_health_disk_rate_label)
        form.addRow("Writer duty", self.logger_health_writer_duty_label)
        form.addRow("Last scope operation", self.logger_health_scope_time_label)
        form.addRow("Queue pressure", self.logger_health_queue_pressure)
        form.addRow("Queue peak memory", self.logger_health_queue_peak_memory_label)
        form.addRow("Current segment size", self.logger_health_segment_bytes_label)
        form.addRow("Total written", self.logger_health_total_bytes_label)
        form.addRow("Measurement rows", self.logger_health_measurement_rows_label)
        form.addRow("Decoded BUS events", self.logger_health_bus_events_label)
        form.addRow("Last record", self.logger_health_last_record_label)
        form.addRow("Last record status", self.logger_health_last_record_status_label)
        form.addRow("Last record UTC", self.logger_health_last_record_utc_label)
        form.addRow("Writer state", self.logger_health_writer_state_label)
        form.addRow("Scope resource", self.logger_health_resource_label)
        form.addRow("Scope identity", self.logger_health_idn_label)
        form.addRow("Session policy", self.logger_health_session_label)
        form.addRow("Recovery", self.logger_health_recovery_label)
        form.addRow("Last error", self.logger_health_last_error_label)
        form.addRow("Disk runway at avg rate", self.logger_health_disk_runway_label)

        note = QLabel(
            "Waveform throughput and scope waveform payload are Logger-observed transfer rates. "
            "They are not the oscilloscope acquisition sample rate."
        )
        note.setObjectName("MutedLabel")
        note.setWordWrap(True)
        form.addRow(note)
        return card

    def start_logger(self) -> None:
        if self._logger_active() or self._logger_writer_active():
            return
        self._logger_health.reset()
        self._logger_health_started_monotonic = None
        self._logger_health_ended_monotonic = None
        super().start_logger()
        if self._logger_active():
            started = self._logger_statistics.started_monotonic
            self._logger_health_started_monotonic = started or time.monotonic()
            self._logger_refresh_status()

    def stop_logger(self) -> None:
        had_run = self._logger_health_started_monotonic is not None
        super().stop_logger()
        if had_run and self._logger_health_ended_monotonic is None:
            self._logger_health_ended_monotonic = time.monotonic()
        self._logger_refresh_status()

    def _run_action(self, description, callback):
        started = time.monotonic()
        result = super()._run_action(description, callback)
        elapsed = max(0.0, time.monotonic() - started)
        if isinstance(result, LoggerRecord):
            self._logger_health.note_capture(result, elapsed)
        return result

    def _logger_health_elapsed(self) -> float:
        started = self._logger_health_started_monotonic
        if started is None:
            return 0.0
        if self._logger_health_ended_monotonic is not None:
            end = self._logger_health_ended_monotonic
        elif self._logger_active() or self._logger_writer_active():
            end = time.monotonic()
        else:
            end = time.monotonic()
            self._logger_health_ended_monotonic = end
        return max(0.0, end - started)

    @staticmethod
    def _format_duration(seconds: float) -> str:
        value = max(0.0, float(seconds))
        if value < 60.0:
            return f"{value:.1f} s"
        if value < 3600.0:
            return f"{value / 60.0:.1f} min"
        if value < 86400.0:
            return f"{value / 3600.0:.1f} h"
        return f"{value / 86400.0:.1f} d"

    @staticmethod
    def _format_bytes(value: int) -> str:
        amount = max(0, int(value))
        if amount >= 1_000_000_000:
            return f"{amount / 1_000_000_000:.2f} GB"
        return f"{amount / 1_000_000:.1f} MB"

    def _logger_writer_state_text(self, snapshot) -> str:
        if snapshot.error:
            return "Error"
        if self._logger_writer_active():
            return "Accepting" if snapshot.accepting else "Draining"
        if snapshot.stopped:
            return "Stopped"
        return "Idle"

    def _logger_resource_text(self) -> str:
        try:
            return str(self._selected_resource())
        except Exception:
            return "--"

    def _logger_disk_runway(self, bytes_per_s: float) -> str:
        if bytes_per_s <= 0.0:
            return "--"
        try:
            root = self._logger_root()
            probe = root if root.exists() else root.parent
            free = int(shutil.disk_usage(probe).free)
        except Exception:
            return "--"
        return self._format_duration(free / bytes_per_s)

    def _logger_refresh_status(self) -> None:
        super()._logger_refresh_status()
        elapsed = self._logger_health_elapsed()
        capture = self._logger_health.snapshot()
        writer_snapshot = self._writer_snapshot()
        writer = self._logger_writer
        policy = writer.policy if writer is not None else None
        if policy is None:
            try:
                policy = self._selected_buffer_policy()
            except Exception:
                policy = None
        metrics = compute_logger_health(
            capture,
            writer_snapshot,
            elapsed_s=elapsed,
            buffer_policy=policy,
        )

        def set_text(name: str, text: str) -> None:
            label = getattr(self, name, None)
            if label is not None:
                label.setText(text)

        set_text("logger_health_elapsed_label", self._format_duration(metrics.elapsed_s))
        set_text("logger_health_captured_label", str(capture.captured_records))
        set_text(
            "logger_health_capture_rate_label",
            f"{metrics.capture_records_per_s:.3f} records/s",
        )
        set_text(
            "logger_health_points_rate_label",
            f"{metrics.waveform_points_per_s:,.0f} points/s",
        )
        set_text(
            "logger_health_scope_payload_label",
            f"{metrics.scope_payload_bytes_per_s / 1_000_000:.3f} MB/s",
        )
        set_text(
            "logger_health_disk_rate_label",
            f"{metrics.disk_bytes_per_s / 1_000_000:.3f} MB/s",
        )
        set_text(
            "logger_health_writer_duty_label",
            f"{metrics.writer_duty_fraction * 100.0:.1f} %",
        )
        set_text(
            "logger_health_scope_time_label",
            f"{capture.last_scope_operation_s:.3f} s",
        )
        set_text(
            "logger_health_queue_peak_memory_label",
            f"{writer_snapshot.peak_bytes / (1024 * 1024):.1f} MB",
        )
        set_text(
            "logger_health_segment_bytes_label",
            self._format_bytes(writer_snapshot.current_segment_bytes),
        )
        set_text(
            "logger_health_total_bytes_label",
            self._format_bytes(writer_snapshot.bytes_written),
        )
        set_text("logger_health_measurement_rows_label", str(capture.measurement_rows))
        set_text("logger_health_bus_events_label", str(capture.bus_events))
        set_text(
            "logger_health_last_record_label",
            "--" if capture.last_record_sequence is None else str(capture.last_record_sequence),
        )
        set_text(
            "logger_health_last_record_status_label",
            "--"
            if capture.last_record_sequence is None
            else ("PARTIAL" if capture.last_record_partial else "Complete"),
        )
        set_text(
            "logger_health_last_record_utc_label",
            capture.last_record_utc or "--",
        )
        set_text(
            "logger_health_writer_state_label",
            self._logger_writer_state_text(writer_snapshot),
        )
        set_text("logger_health_resource_label", self._logger_resource_text())
        identity = str(getattr(self, "_last_idn", "") or "").strip()
        set_text("logger_health_idn_label", identity if identity and not identity.startswith("Error:") else "--")
        keep = getattr(self, "keep_session", None)
        persistent = bool(keep is not None and keep.isChecked())
        connection = "connected" if bool(getattr(self, "_connection_ok", False)) else "disconnected"
        set_text(
            "logger_health_session_label",
            f"{'Persistent' if persistent else 'Short-lived'} / {connection}",
        )
        recovery = getattr(self, "_recovery_statistics", None)
        reconnects = int(getattr(recovery, "reconnects", 0))
        retries = int(getattr(recovery, "retry_attempts", 0))
        set_text(
            "logger_health_recovery_label",
            f"{reconnects} reconnects / {retries} retries",
        )
        last_error = (
            str(getattr(self._logger_statistics, "last_error", "") or "")
            or str(writer_snapshot.error or "")
            or str(getattr(recovery, "last_error", "") or "")
        )
        set_text("logger_health_last_error_label", last_error or "--")
        set_text(
            "logger_health_disk_runway_label",
            self._logger_disk_runway(metrics.disk_bytes_per_s),
        )

        rate_label = getattr(self, "logger_rate_label", None)
        if rate_label is not None:
            rate_label.setText(f"{metrics.effective_records_per_s:.3f} records/s")

        pressure = getattr(self, "logger_health_queue_pressure", None)
        if pressure is not None:
            fraction = max(metrics.queue_record_fraction, metrics.queue_byte_fraction)
            pressure.setValue(int(round(fraction * 1000.0)))
            pressure.setFormat(f"{fraction * 100.0:.1f} %")


__all__ = ["QtScopeWindow"]
