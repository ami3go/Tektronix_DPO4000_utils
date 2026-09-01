"""Logger L4 CSV/Binary output selection with DPO4LOG."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel

from ..logger.models import LoggerOutputFormat, LoggerRecord, LoggerState, LoggerStatistics
from ..logger.output import LoggerOutputSession
from ..logger.producer import capture_logger_record
from .logger_math_window import QtScopeWindow as LoggerL2QtScopeWindow
from .logger_page_layout import FILE_PAGE_INDEX


class QtScopeWindow(LoggerL2QtScopeWindow):
    """L2 source selection plus L3 CSV segments and L4 DPO4LOG binary output."""

    def __init__(self, *args, **kwargs) -> None:
        self._logger_output_session: LoggerOutputSession | None = None
        super().__init__(*args, **kwargs)

    def _build_logger_output_card(self):
        card = self._card("Output")
        form = QFormLayout(card)
        self._prepare_form(form)
        self.logger_output_format = QComboBox()
        self.logger_output_format.addItems([item.value for item in LoggerOutputFormat])
        self.logger_output_format.setCurrentText(LoggerOutputFormat.BINARY.value)
        form.addRow("Format", self.logger_output_format)
        hint = QLabel(
            "CSV appends acquisition blocks to one run segment. Binary DPO4LOG stores compact raw samples and full scaling metadata in CRC-protected frames."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        form.addRow(hint)
        return self._prepare_drawer_card(card)

    def _selected_output_format(self) -> LoggerOutputFormat:
        return LoggerOutputFormat(self.logger_output_format.currentText())

    def _logger_refresh_status(self) -> None:
        super()._logger_refresh_status()
        combo = getattr(self, "logger_output_format", None)
        if combo is not None:
            combo.setEnabled(not self._logger_active() and not bool(getattr(self, "_operation_active", False)))

    def _open_logger_output(self, config) -> LoggerOutputSession:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        root = Path(self.output_folder.text()).expanduser() / "logger"
        return LoggerOutputSession(
            root,
            self._selected_output_format(),
            run_metadata={
                "mode": config.mode.value,
                "waveform_sources": list(config.waveform_sources),
                "encoding": config.encoding,
                "sample_width": config.sample_width,
            },
        )

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
            output = self._open_logger_output(config)
        except Exception as exc:  # noqa: BLE001 - validate output before instrument activity.
            self._message("Logger", f"Could not start Logger output: {exc}", error=True)
            return
        self._logger_output_session = output
        self._logger_config_active = config
        self._logger_state = LoggerState.RUNNING
        self._logger_statistics = LoggerStatistics(started_monotonic=time.monotonic())
        self._logger_sequence = 0
        self._logger_last_file = output.paths[0] if output.paths else None
        timer = self._logger_timer
        if timer is None:
            try:
                output.close()
            finally:
                self._logger_output_session = None
                self._logger_state = LoggerState.FAILED
            self._message("Logger", "Logger timer is unavailable.", error=True)
            return
        timer.setInterval(max(1, int(round(config.interval_s * 1000.0))))
        timer.start()
        self._append_log(
            f"Logger started: {', '.join(config.waveform_sources)} -> {output.output_format.value}"
        )
        self.statusBar().showMessage(f"Logger running: {output.output_format.value}")
        self._logger_refresh_status()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._logger_tick)

    def stop_logger(self) -> None:
        timer = self._logger_timer
        if timer is not None:
            timer.stop()
        was_active = self._logger_active()
        output = self._logger_output_session
        self._logger_output_session = None
        close_error = ""
        if output is not None:
            try:
                output.close()
                self._logger_statistics.bytes_written = output.bytes_written
            except Exception as exc:  # noqa: BLE001 - report close/final-frame failures.
                close_error = str(exc)
                self._logger_statistics.failed += 1
                self._logger_statistics.last_error = close_error
        self._logger_state = LoggerState.FAILED if close_error else LoggerState.IDLE
        self._logger_config_active = None
        if was_active:
            self._append_log(f"Logger stopped{': ' + close_error if close_error else ''}")
        self._logger_refresh_status()

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
        try:
            result = self._run_action(
                f"Logger capture #{sequence:08d}",
                lambda scope: capture_logger_record(scope, config, sequence),
            )
            if not isinstance(result, LoggerRecord):
                raise RuntimeError(str(getattr(self, "_last_action", "Logger capture failed")))
            self._logger_statistics.records_captured += 1
            output.append(result)
            self._logger_statistics.records_written = output.records_written
            self._logger_statistics.bytes_written = output.bytes_written
            self._logger_statistics.last_error = ""
            self._logger_last_file = output.paths[-1] if output.paths else None
            self.statusBar().showMessage(f"Logger record {sequence} written")
        except Exception as exc:  # noqa: BLE001 - stop on acquisition or output corruption risk.
            self._logger_statistics.failed += 1
            self._logger_statistics.last_error = str(exc)
            self._logger_state = LoggerState.FAILED
            timer = self._logger_timer
            if timer is not None:
                timer.stop()
            try:
                output.close()
            except Exception as close_exc:  # noqa: BLE001
                self._append_log(f"Logger output close after failure also failed: {close_exc}")
            self._logger_output_session = None
            self._append_log(f"Logger L4 failed: {exc}")
            self.statusBar().showMessage("Logger failed")
        finally:
            self._logger_busy = False
            self._logger_refresh_status()


__all__ = ["QtScopeWindow"]
