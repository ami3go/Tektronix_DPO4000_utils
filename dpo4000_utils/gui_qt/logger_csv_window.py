"""Logger L3 append-only waveform CSV segments."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..logger.csv_stream import WaveformCsvStreamWriter
from ..logger.models import LoggerRecord, LoggerState
from ..logger.producer import capture_logger_record
from .logger_math_window import QtScopeWindow as LoggerL2QtScopeWindow
from .logger_page_layout import FILE_PAGE_INDEX


class QtScopeWindow(LoggerL2QtScopeWindow):
    """L2 Logger with one append-only CSV segment per run."""

    def __init__(self, *args, **kwargs) -> None:
        self._logger_csv_writer: WaveformCsvStreamWriter | None = None
        super().__init__(*args, **kwargs)

    def _build_logger_output_card(self):
        card = super()._build_logger_output_card()
        layout = card.layout()
        if layout is not None:
            from PySide6.QtWidgets import QLabel

            label = QLabel(
                "L3 output: records are appended to one run CSV segment instead of creating one file per acquisition. "
                "Each completed record is flushed before the next record is accepted."
            )
            label.setWordWrap(True)
            layout.addWidget(label)
        return card

    def _logger_csv_path(self) -> Path:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        root = Path(self.output_folder.text()).expanduser() / "logger"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        return root / f"waveform_{stamp}_0000.csv"

    def start_logger(self) -> None:
        if self._logger_active():
            return
        try:
            writer = WaveformCsvStreamWriter(self._logger_csv_path())
        except Exception as exc:  # noqa: BLE001 - output validation must fail before instrument activity.
            self._message("Logger", f"Could not create Logger CSV segment: {exc}", error=True)
            return
        self._logger_csv_writer = writer
        super().start_logger()
        if not self._logger_active():
            writer.close()
            self._logger_csv_writer = None

    def stop_logger(self) -> None:
        writer = self._logger_csv_writer
        self._logger_csv_writer = None
        try:
            if writer is not None:
                writer.close()
        finally:
            super().stop_logger()

    def _logger_tick(self) -> None:
        if self._logger_state is not LoggerState.RUNNING:
            return
        if self._logger_busy:
            self._logger_statistics.skipped += 1
            self._logger_refresh_status()
            return
        config = self._logger_config_active
        writer = self._logger_csv_writer
        if config is None or writer is None:
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
            writer.append(result)
            self._logger_statistics.records_written = writer.records_written
            self._logger_statistics.bytes_written = writer.bytes_written
            self._logger_statistics.last_error = ""
            self._logger_last_file = writer.path
            self.statusBar().showMessage(f"Logger record {sequence} appended: {writer.path.name}")
        except Exception as exc:  # noqa: BLE001 - stop safely on acquisition/output failure.
            self._logger_statistics.failed += 1
            self._logger_statistics.last_error = str(exc)
            self._logger_state = LoggerState.FAILED
            timer = self._logger_timer
            if timer is not None:
                timer.stop()
            try:
                writer.close()
            finally:
                self._logger_csv_writer = None
            self._append_log(f"Logger L3 failed: {exc}")
            self.statusBar().showMessage("Logger failed")
        finally:
            self._logger_busy = False
            self._logger_refresh_status()


__all__ = ["QtScopeWindow"]
