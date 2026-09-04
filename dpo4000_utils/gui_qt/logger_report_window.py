"""Logger L14 crash-tolerant run reporting."""

from __future__ import annotations

import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QWidget

from ..logger.health import compute_logger_health
from ..logger.profiles import validate_logger_profile_config
from ..logger.reporting import LoggerRunReporter
from .logger_health_window import QtScopeWindow as LoggerL13QtScopeWindow

_REPORT_CHECKPOINT_INTERVAL_S = 30.0


class QtScopeWindow(LoggerL13QtScopeWindow):
    """L13 Logger extended with durable checkpoints and final run summaries."""

    def __init__(self, *args, **kwargs) -> None:
        self._logger_reporter: LoggerRunReporter | None = None
        self._logger_report_path: Path | None = None
        self._logger_report_stop_reason = ""
        self._logger_report_failed = False
        self._logger_report_next_checkpoint = 0.0
        self._logger_report_last_rotation = 0
        self._logger_report_last_reconnects = 0
        self._logger_report_last_retries = 0
        self._logger_report_last_deleted_segments = 0
        self._logger_report_last_error = ""
        super().__init__(*args, **kwargs)

    def _build_logger_health_card(self):
        card = super()._build_logger_health_card()
        form = card.layout()
        if not isinstance(form, QFormLayout):
            return card

        self.logger_report_path_label = QLabel("--")
        self.logger_report_path_label.setWordWrap(True)
        controls = QWidget()
        layout = QHBoxLayout(controls)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._button("Open report", self.open_logger_report))
        layout.addWidget(self._button("Open report folder", self.open_logger_report_folder))
        form.addRow("Run report", self.logger_report_path_label)
        form.addRow(controls)
        return card

    @staticmethod
    def _logger_package_version() -> str:
        try:
            return version("dpo4000-utils")
        except PackageNotFoundError:
            return "unknown"

    def _logger_report_config_snapshot(self) -> dict:
        return validate_logger_profile_config(self._collect_logger_profile_config())

    def _logger_report_display_path(self) -> Path | None:
        reporter = self._logger_reporter
        if self._logger_report_path is not None:
            return self._logger_report_path
        if reporter is None:
            return None
        if reporter.summary_path.exists():
            return reporter.summary_path
        if reporter.checkpoint_path.exists():
            return reporter.checkpoint_path
        return reporter.event_jsonl_path

    def open_logger_report(self) -> None:
        path = self._logger_report_display_path()
        if path is None or not path.exists():
            self._message("Logger report", "No Logger report is available yet.", error=True)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_logger_report_folder(self) -> None:
        path = self._logger_report_display_path()
        if path is None:
            reporter = self._logger_reporter
            if reporter is None:
                self._message(
                    "Logger report",
                    "No Logger report folder is available yet.",
                    error=True,
                )
                return
            folder = reporter.root
        else:
            folder = path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _report_relative_path(self, path: str | Path) -> str:
        candidate = Path(path).expanduser()
        try:
            root = self._logger_root().resolve()
            return str(candidate.resolve().relative_to(root))
        except (OSError, ValueError):
            return str(candidate)

    def _logger_report_state(self) -> dict:
        capture = self._logger_health.snapshot()
        writer = self._writer_snapshot()
        elapsed = self._logger_health_elapsed()
        active_writer = self._logger_writer
        policy = active_writer.policy if active_writer is not None else None
        if policy is None:
            try:
                policy = self._selected_buffer_policy()
            except Exception:
                policy = None
        metrics = compute_logger_health(
            capture,
            writer,
            elapsed_s=elapsed,
            buffer_policy=policy,
        )

        recovery = getattr(self, "_recovery_statistics", None)
        recovery_state = {
            "retry_attempts": int(getattr(recovery, "retry_attempts", 0)),
            "reconnects": int(getattr(recovery, "reconnects", 0)),
            "transport_failures": int(getattr(recovery, "transport_failures", 0)),
            "consecutive_failures": int(getattr(recovery, "consecutive_failures", 0)),
            "last_error": str(getattr(recovery, "last_error", "") or ""),
        }

        retention_manager = getattr(self, "_logger_retention_manager", None)
        retention_stats = (
            retention_manager.statistics if retention_manager is not None else None
        )
        registered_segments = (
            retention_manager.registered_segments if retention_manager is not None else ()
        )
        output_segments = [
            [self._report_relative_path(path) for path in segment]
            for segment in registered_segments
        ]
        current_paths = [self._report_relative_path(path) for path in writer.output_paths]

        captured = int(capture.captured_records)
        written = int(writer.written_records)
        dropped = int(writer.dropped_records)
        queued = int(writer.queued_records)
        accounted = written + dropped + queued
        reconciliation = {
            "records_captured": captured,
            "records_accounted_by_writer": accounted,
            "unaccounted_records": captured - accounted,
            "records_reconciled": captured == accounted,
            "writer_queue_empty": queued == 0,
            "writer_stopped": bool(writer.stopped),
        }

        return {
            "logger_state": self._logger_state.value,
            "elapsed_s": metrics.elapsed_s,
            "records": {
                "produced": captured,
                "written": written,
                "skipped": int(self._logger_statistics.skipped),
                "dropped": dropped,
                "errors": int(self._logger_statistics.failed),
            },
            "payload_totals": {
                "waveform_points": int(capture.waveform_points),
                "waveform_payload_bytes": int(capture.waveform_payload_bytes),
                "measurement_rows": int(capture.measurement_rows),
                "measurement_values": int(capture.measurement_values),
                "bus_events": int(capture.bus_events),
            },
            "throughput": {
                "captured_records_per_s": metrics.capture_records_per_s,
                "effective_records_per_s": metrics.effective_records_per_s,
                "waveform_points_per_s": metrics.waveform_points_per_s,
                "scope_payload_bytes_per_s": metrics.scope_payload_bytes_per_s,
                "disk_bytes_per_s": metrics.disk_bytes_per_s,
                "writer_duty_fraction": metrics.writer_duty_fraction,
            },
            "writer": {
                "enqueued_records": int(writer.enqueued_records),
                "queued_records": queued,
                "queued_bytes": int(writer.queued_bytes),
                "peak_records": int(writer.peak_records),
                "peak_bytes": int(writer.peak_bytes),
                "overflow_events": int(writer.overflow_events),
                "bytes_written": int(writer.bytes_written),
                "total_write_s": float(writer.total_write_s),
                "last_write_s": float(writer.last_write_s),
                "segment_index": int(writer.segment_index),
                "rotation_count": int(writer.rotation_count),
                "current_segment_bytes": int(writer.current_segment_bytes),
                "current_paths": current_paths,
                "error": str(writer.error or ""),
                "stopped": bool(writer.stopped),
            },
            "output_segments": output_segments,
            "output_segment_count": len(output_segments),
            "output_file_count": sum(len(segment) for segment in output_segments),
            "last_record": {
                "sequence": capture.last_record_sequence,
                "utc": capture.last_record_utc,
                "partial": bool(capture.last_record_partial),
                "scope_operation_s": float(capture.last_scope_operation_s),
            },
            "recovery": recovery_state,
            "retention": {
                "registered_segments": int(
                    getattr(retention_stats, "registered_segments", 0)
                ),
                "deleted_segments": int(getattr(retention_stats, "deleted_segments", 0)),
                "deleted_files": int(getattr(retention_stats, "deleted_files", 0)),
                "reclaimed_bytes": int(getattr(retention_stats, "reclaimed_bytes", 0)),
            },
            "reconciliation": reconciliation,
            "last_error": str(self._logger_statistics.last_error or writer.error or ""),
        }

    def _safe_logger_report_event(
        self,
        event_type: str,
        *,
        details: dict | None = None,
        sequence: int | None = None,
    ) -> None:
        reporter = self._logger_reporter
        if reporter is None or reporter.finalized or self._logger_report_failed:
            return
        try:
            reporter.append_event(event_type, details=details, sequence=sequence)
        except Exception as exc:  # noqa: BLE001 - reporting failure is handled fail-closed.
            self._logger_report_failed = True
            self._append_log(f"Logger report event write failed: {exc}")

    def _checkpoint_logger_report(self, *, reason: str, force: bool = False) -> None:
        reporter = self._logger_reporter
        if reporter is None or reporter.finalized or self._logger_report_failed:
            return
        now = time.monotonic()
        if not force and now < self._logger_report_next_checkpoint:
            return
        try:
            self._logger_report_path = reporter.checkpoint(
                self._logger_report_state(), reason=reason
            )
            self._logger_report_next_checkpoint = now + _REPORT_CHECKPOINT_INTERVAL_S
        except Exception as exc:  # noqa: BLE001 - report durability is required for L14.
            self._logger_report_failed = True
            self._logger_report_stop_reason = "report_failure"
            message = f"Logger report checkpoint failed: {exc}"
            self._append_log(message)
            if self._logger_active() or self._logger_writer_active():
                LoggerL13QtScopeWindow._fail_buffered_logger(self, message)

    def _finalize_logger_report(self, *, reason: str | None = None) -> None:
        reporter = self._logger_reporter
        if reporter is None or reporter.finalized or self._logger_writer_active():
            return
        stop_reason = reason or self._logger_report_stop_reason or "stopped"
        state = self._logger_report_state()
        final_error = str(state.get("last_error", "") or "")
        try:
            if not self._logger_report_failed:
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
            self._logger_report_path = reporter.finalize(
                stop_reason=stop_reason,
                state=state,
                final_error=final_error,
            )
            self._append_log(f"Logger run report finalized: {self._logger_report_path}")
        except Exception as exc:  # noqa: BLE001 - shutdown must continue if reporting fails.
            self._logger_report_failed = True
            self._append_log(f"Logger report finalization failed: {exc}")

    def start_logger(self) -> None:
        if self._logger_active() or self._logger_writer_active():
            return
        try:
            config = self._logger_report_config_snapshot()
            report_root = self._logger_root() / "reports"
            profile = getattr(self, "logger_profile_name", None)
            profile_name = profile.text().strip() if profile is not None else ""
            identity = str(getattr(self, "_last_idn", "") or "").strip()
            if identity.startswith("Error:"):
                identity = ""
            reporter = LoggerRunReporter(
                report_root,
                config=config,
                package_version=self._logger_package_version(),
                profile_name=profile_name,
                resource=self._logger_resource_text(),
                idn=identity,
            )
            reporter.append_event(
                "RUN_STARTING",
                details={"mode": config["mode"], "output_format": config["output_format"]},
            )
        except Exception as exc:  # noqa: BLE001 - report setup must block unattended logging.
            self._message("Logger report", f"Could not initialize run report: {exc}", error=True)
            return

        self._logger_reporter = reporter
        self._logger_report_path = reporter.event_jsonl_path
        self._logger_report_stop_reason = ""
        self._logger_report_failed = False
        self._logger_report_next_checkpoint = 0.0
        self._logger_report_last_rotation = 0
        self._logger_report_last_reconnects = 0
        self._logger_report_last_retries = 0
        self._logger_report_last_deleted_segments = 0
        self._logger_report_last_error = ""

        super().start_logger()
        if self._logger_active():
            identity = str(getattr(self, "_last_idn", "") or "").strip()
            if identity and not identity.startswith("Error:"):
                reporter.idn = identity
            self._safe_logger_report_event(
                "RUN_STARTED",
                details={"state": self._logger_state.value},
            )
            self._checkpoint_logger_report(reason="run_started", force=True)
        else:
            self._logger_report_stop_reason = "start_failed"
            self._safe_logger_report_event(
                "RUN_START_FAILED",
                details={"error": str(self._logger_statistics.last_error or "")},
            )
            if self._logger_writer_active():
                self._checkpoint_logger_report(reason="start_failed", force=True)
            else:
                self._finalize_logger_report(reason="start_failed")
        self._logger_refresh_status()

    def pause_resume_logger(self) -> None:
        before = self._logger_state
        super().pause_resume_logger()
        after = self._logger_state
        if after is not before:
            event_type = "PAUSED" if after.value == "Paused" else "RESUMED"
            self._safe_logger_report_event(event_type, details={"state": after.value})
            self._checkpoint_logger_report(reason=event_type.lower(), force=True)

    def stop_logger(self) -> None:
        was_active = self._logger_active() or self._logger_writer_active()
        if was_active and not self._logger_report_stop_reason:
            self._logger_report_stop_reason = "operator_stop"
            self._safe_logger_report_event(
                "STOP_REQUESTED",
                sequence=self._logger_sequence or None,
            )
        super().stop_logger()
        if was_active:
            if self._logger_writer_active():
                self._checkpoint_logger_report(reason="stop_waiting_for_writer", force=True)
            else:
                self._finalize_logger_report()
        self._logger_refresh_status()

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
        )
        super()._fail_buffered_logger(
            message,
            count_failure=count_failure,
            writer_error=writer_error,
        )
        self._checkpoint_logger_report(reason="failure", force=True)

    def _logger_report_runtime_events(self) -> None:
        reporter = self._logger_reporter
        if reporter is None or reporter.finalized:
            return
        writer = self._writer_snapshot()
        if writer.rotation_count > self._logger_report_last_rotation:
            self._safe_logger_report_event(
                "ROTATION",
                sequence=self._logger_sequence or None,
                details={
                    "rotation_count": int(writer.rotation_count),
                    "segment_index": int(writer.segment_index),
                },
            )
            self._logger_report_last_rotation = int(writer.rotation_count)

        recovery = getattr(self, "_recovery_statistics", None)
        reconnects = int(getattr(recovery, "reconnects", 0))
        retries = int(getattr(recovery, "retry_attempts", 0))
        if (
            reconnects > self._logger_report_last_reconnects
            or retries > self._logger_report_last_retries
        ):
            self._safe_logger_report_event(
                "RECOVERY",
                sequence=self._logger_sequence or None,
                details={"reconnects": reconnects, "retry_attempts": retries},
            )
            self._logger_report_last_reconnects = reconnects
            self._logger_report_last_retries = retries

        retention_manager = getattr(self, "_logger_retention_manager", None)
        retention_stats = (
            retention_manager.statistics if retention_manager is not None else None
        )
        deleted = int(getattr(retention_stats, "deleted_segments", 0))
        if deleted > self._logger_report_last_deleted_segments:
            self._safe_logger_report_event(
                "RETENTION",
                details={
                    "deleted_segments": deleted,
                    "deleted_files": int(getattr(retention_stats, "deleted_files", 0)),
                    "reclaimed_bytes": int(
                        getattr(retention_stats, "reclaimed_bytes", 0)
                    ),
                },
            )
            self._logger_report_last_deleted_segments = deleted

        error = str(self._logger_statistics.last_error or writer.error or "")
        if error and error != self._logger_report_last_error:
            self._safe_logger_report_event(
                "ERROR",
                sequence=self._logger_sequence or None,
                details={"message": error},
            )
            self._logger_report_last_error = error

    def _logger_writer_monitor_tick(self) -> None:
        super()._logger_writer_monitor_tick()
        self._logger_report_runtime_events()
        if self._logger_active() or self._logger_writer_active():
            self._checkpoint_logger_report(reason="periodic")
        elif self._logger_state.value == "Failed" or self._logger_report_stop_reason:
            reason = self._logger_report_stop_reason or "logger_failure"
            self._finalize_logger_report(reason=reason)
        self._logger_refresh_status()

    def _logger_refresh_status(self) -> None:
        super()._logger_refresh_status()
        label = getattr(self, "logger_report_path_label", None)
        if label is not None:
            path = self._logger_report_display_path()
            label.setText(str(path) if path is not None else "--")


__all__ = ["QtScopeWindow"]
