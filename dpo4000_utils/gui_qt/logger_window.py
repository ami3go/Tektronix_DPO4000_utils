"""Logger L1 Analog Waveform Logger tab."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..automation import collision_safe_path
from ..logger.csv_record import write_waveform_record_csv
from ..logger.models import LoggerConfig, LoggerMode, LoggerRecord, LoggerState, LoggerStatistics
from ..logger.producer import capture_logger_record
from .automation_report_review_window import QtScopeWindow as AutomationA12ReviewedQtScopeWindow
from .logger_page_layout import FILE_PAGE_INDEX, install_logger_page_layout

install_logger_page_layout()


class QtScopeWindow(AutomationA12ReviewedQtScopeWindow):
    """Automation-complete desktop extended with L1 CH1..CH4 waveform logging."""

    def __init__(self, *args, **kwargs) -> None:
        self._logger_state = LoggerState.IDLE
        self._logger_statistics = LoggerStatistics()
        self._logger_timer: QTimer | None = None
        self._logger_busy = False
        self._logger_sequence = 0
        self._logger_last_file: Path | None = None
        self._logger_config_active: LoggerConfig | None = None
        super().__init__(*args, **kwargs)
        self._logger_timer = QTimer(self)
        self._logger_timer.setSingleShot(False)
        self._logger_timer.timeout.connect(self._logger_tick)

    def _build_logger_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)
        layout.addWidget(self._build_logger_status_card())
        layout.addWidget(self._build_logger_sources_card())
        layout.addWidget(self._build_logger_acquisition_card())
        layout.addWidget(self._build_logger_output_card())
        layout.addWidget(self._build_logger_health_card())
        layout.addStretch(1)
        self._logger_refresh_status()
        return self._wrap_scrollable_drawer_page(
            body,
            scroll_name="LoggerScrollArea",
            body_name="LoggerScrollBody",
        )

    def _build_logger_status_card(self):
        card = self._card("Logger Status & Control")
        form = QFormLayout(card)
        self._prepare_form(form)
        self.logger_state_label = QLabel("Idle")
        self.logger_mode_label = QLabel(LoggerMode.WAVEFORM.value)
        form.addRow("State", self.logger_state_label)
        form.addRow("Mode", self.logger_mode_label)
        buttons = QHBoxLayout()
        self.logger_start_button = self._accent_button("Start", self.start_logger)
        self.logger_pause_button = self._button("Pause", self.pause_resume_logger)
        self.logger_stop_button = self._button("Stop", self.stop_logger)
        for button in (self.logger_start_button, self.logger_pause_button, self.logger_stop_button):
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            buttons.addWidget(button, 1)
        form.addRow(buttons)
        return self._prepare_drawer_card(card)

    def _build_logger_sources_card(self):
        card = self._card("Sources")
        form = QFormLayout(card)
        self._prepare_form(form)
        self.logger_channel_checks: dict[str, QCheckBox] = {}
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        for index in range(1, 5):
            source = f"CH{index}"
            check = QCheckBox(source)
            check.setChecked(index == 1)
            self.logger_channel_checks[source] = check
            row_layout.addWidget(check)
        form.addRow("Analog", row)
        hint = QLabel("L1 reads selected CH1..CH4 finite records through the public binary waveform API.")
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        form.addRow(hint)
        return self._prepare_drawer_card(card)

    def _build_logger_acquisition_card(self):
        card = self._card("Acquisition")
        form = QFormLayout(card)
        self._prepare_form(form)
        self.logger_interval = QDoubleSpinBox()
        self.logger_interval.setRange(0.1, 604800.0)
        self.logger_interval.setDecimals(3)
        self.logger_interval.setValue(1.0)
        self.logger_interval.setSuffix(" s")
        form.addRow("Record interval", self.logger_interval)
        hint = QLabel(
            "Each tick transfers one finite scope record. Effective rate is limited by record length, "
            "selected sources, VISA transport and disk write time. Busy ticks are skipped, never queued."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        form.addRow(hint)
        return self._prepare_drawer_card(card)

    def _build_logger_output_card(self):
        card = self._card("Output")
        layout = QVBoxLayout(card)
        label = QLabel(
            "L1 writes one collision-safe CSV per acquisition under File → Destination folder / logger/. "
            "L3 replaces this bootstrap persistence with append/streaming CSV; L4 adds DPO4LOG binary."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        return self._prepare_drawer_card(card)

    def _build_logger_health_card(self):
        card = self._card("Runtime Health")
        form = QFormLayout(card)
        self._prepare_form(form)
        self.logger_records_label = QLabel("0")
        self.logger_skipped_label = QLabel("0")
        self.logger_failed_label = QLabel("0")
        self.logger_rate_label = QLabel("0.000 records/s")
        self.logger_last_file_label = QLabel("--")
        self.logger_last_file_label.setWordWrap(True)
        form.addRow("Records", self.logger_records_label)
        form.addRow("Skipped busy ticks", self.logger_skipped_label)
        form.addRow("Failed", self.logger_failed_label)
        form.addRow("Effective rate", self.logger_rate_label)
        form.addRow("Last file", self.logger_last_file_label)
        return self._prepare_drawer_card(card)

    def _logger_selected_sources(self) -> tuple[str, ...]:
        return tuple(source for source, check in self.logger_channel_checks.items() if check.isChecked())

    def _logger_config(self) -> LoggerConfig:
        return LoggerConfig(
            mode=LoggerMode.WAVEFORM,
            interval_s=float(self.logger_interval.value()),
            waveform_sources=self._logger_selected_sources(),
        )

    def _logger_active(self) -> bool:
        return self._logger_state in {LoggerState.RUNNING, LoggerState.PAUSED}

    def _logger_refresh_status(self) -> None:
        state_label = getattr(self, "logger_state_label", None)
        if state_label is None:
            return
        state_label.setText(self._logger_state.value)
        stats = self._logger_statistics
        self.logger_records_label.setText(str(stats.records_written))
        self.logger_skipped_label.setText(str(stats.skipped))
        self.logger_failed_label.setText(str(stats.failed))
        elapsed = 0.0
        if stats.started_monotonic is not None:
            elapsed = max(0.0, time.monotonic() - stats.started_monotonic)
        rate = stats.records_written / elapsed if elapsed > 0 else 0.0
        self.logger_rate_label.setText(f"{rate:.3f} records/s")
        self.logger_last_file_label.setText(str(self._logger_last_file) if self._logger_last_file else "--")
        operation_active = bool(getattr(self, "_operation_active", False))
        connection_ok = bool(getattr(self, "_connection_ok", False))
        automation_active = self._automation_any_active()
        editable = not self._logger_active() and not operation_active
        self.logger_start_button.setEnabled(editable and connection_ok and not automation_active)
        self.logger_pause_button.setEnabled(self._logger_active())
        self.logger_pause_button.setText("Resume" if self._logger_state is LoggerState.PAUSED else "Pause")
        self.logger_stop_button.setEnabled(self._logger_active())
        self.logger_interval.setEnabled(editable)
        for check in self.logger_channel_checks.values():
            check.setEnabled(editable)

    def _update_scope_control_enabled(self) -> None:
        super()._update_scope_control_enabled()
        self._logger_refresh_status()

    def start_logger(self) -> None:
        if self._logger_active():
            return
        if self._automation_any_active():
            self._message("Logger", "Stop Automation before starting Logger.", error=True)
            return
        if not bool(getattr(self, "_connection_ok", False)):
            self._message("Logger", "Test the scope connection before starting Logger.", error=True)
            return
        try:
            self._ensure_control_page_built(FILE_PAGE_INDEX)
            config = self._logger_config()
        except Exception as exc:  # noqa: BLE001 - exact configuration feedback.
            self._message("Logger", str(exc), error=True)
            return
        self._logger_config_active = config
        self._logger_state = LoggerState.RUNNING
        self._logger_statistics = LoggerStatistics(started_monotonic=time.monotonic())
        self._logger_sequence = 0
        self._logger_last_file = None
        timer = self._logger_timer
        if timer is None:
            self._logger_state = LoggerState.FAILED
            self._message("Logger", "Logger timer is unavailable.", error=True)
            return
        timer.setInterval(max(1, int(round(config.interval_s * 1000.0))))
        timer.start()
        self._append_log(f"Logger L1 started: {', '.join(config.waveform_sources)} every {config.interval_s:g} s")
        self.statusBar().showMessage("Logger running: analog waveform records")
        self._logger_refresh_status()
        QTimer.singleShot(0, self._logger_tick)

    def pause_resume_logger(self) -> None:
        timer = self._logger_timer
        if self._logger_state is LoggerState.RUNNING:
            self._logger_state = LoggerState.PAUSED
            if timer is not None:
                timer.stop()
            self._append_log("Logger paused")
        elif self._logger_state is LoggerState.PAUSED:
            self._logger_state = LoggerState.RUNNING
            config = self._logger_config_active
            if timer is not None and config is not None:
                timer.setInterval(max(1, int(round(config.interval_s * 1000.0))))
                timer.start()
            self._append_log("Logger resumed")
        self._logger_refresh_status()

    def stop_logger(self) -> None:
        timer = self._logger_timer
        if timer is not None:
            timer.stop()
        was_active = self._logger_active()
        self._logger_state = LoggerState.IDLE
        self._logger_config_active = None
        if was_active:
            self._append_log("Logger stopped")
            self.statusBar().showMessage("Logger stopped")
        self._logger_refresh_status()

    def _logger_output_path(self, sequence: int) -> Path:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        root = Path(self.output_folder.text()).expanduser() / "logger"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        return collision_safe_path(root / f"waveform_{stamp}_{sequence:08d}.csv")

    def _logger_tick(self) -> None:
        if self._logger_state is not LoggerState.RUNNING:
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
        try:
            result = self._run_action(
                f"Logger capture #{sequence:08d}",
                lambda scope: capture_logger_record(scope, config, sequence),
            )
            if not isinstance(result, LoggerRecord):
                raise RuntimeError(str(getattr(self, "_last_action", "Logger capture failed")))
            self._logger_statistics.records_captured += 1
            path = self._logger_output_path(sequence)
            written = write_waveform_record_csv(path, result)
            self._logger_statistics.records_written += 1
            self._logger_statistics.bytes_written += written.stat().st_size
            self._logger_statistics.last_error = ""
            self._logger_last_file = written
            self.statusBar().showMessage(f"Logger record {sequence} saved: {written.name}")
        except Exception as exc:  # noqa: BLE001 - stop unattended logger on unhandled capture/output failure.
            self._logger_statistics.failed += 1
            self._logger_statistics.last_error = str(exc)
            self._logger_state = LoggerState.FAILED
            timer = self._logger_timer
            if timer is not None:
                timer.stop()
            self._append_log(f"Logger L1 failed: {exc}")
            self.statusBar().showMessage("Logger failed")
        finally:
            self._logger_busy = False
            self._logger_refresh_status()

    def start_automation(self) -> None:
        if self._logger_active():
            self._message("Automation", "Stop Logger before starting Automation.", error=True)
            return
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        super().start_automation()

    def run_automation_once(self) -> None:
        if self._logger_active():
            self._message("Automation", "Stop Logger before running Automation.", error=True)
            return
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        super().run_automation_once()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name.
        self.stop_logger()
        super().closeEvent(event)


__all__ = ["QtScopeWindow"]
