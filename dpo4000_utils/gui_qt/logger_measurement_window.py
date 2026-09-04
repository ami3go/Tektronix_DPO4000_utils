"""Logger L5 measurement time-series mode."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QWidget

from ..logger.models import LoggerConfig, LoggerMode
from ..logger.output import LoggerOutputSession
from .logger_binary_window import QtScopeWindow as LoggerL4QtScopeWindow
from .logger_page_layout import FILE_PAGE_INDEX


class QtScopeWindow(LoggerL4QtScopeWindow):
    """L4 Logger extended with selectable MEAS1..MEAS8 time-series logging."""

    def _build_logger_sources_card(self):
        card = super()._build_logger_sources_card()
        form = card.layout()
        self.logger_mode_combo = QComboBox()
        self.logger_mode_combo.addItems([LoggerMode.WAVEFORM.value, LoggerMode.MEASUREMENTS.value])
        self.logger_mode_combo.currentTextChanged.connect(self._logger_mode_changed)
        self.logger_measurement_checks: dict[int, QCheckBox] = {}
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        for slot in range(1, 9):
            check = QCheckBox(f"MEAS{slot}")
            check.setChecked(slot == 1)
            self.logger_measurement_checks[slot] = check
            row_layout.addWidget(check)
        self.logger_measurement_row = row
        if isinstance(form, QFormLayout):
            form.insertRow(0, "Logger mode", self.logger_mode_combo)
            form.addRow("Measurements", row)
        self._logger_mode_changed()
        return card

    def _logger_mode(self) -> LoggerMode:
        combo = getattr(self, "logger_mode_combo", None)
        return LoggerMode(combo.currentText()) if combo is not None else LoggerMode.WAVEFORM

    def _logger_mode_changed(self, *_args) -> None:
        mode = self._logger_mode()
        row = getattr(self, "logger_measurement_row", None)
        if row is not None:
            row.setVisible(mode is LoggerMode.MEASUREMENTS)
        label = getattr(self, "logger_mode_label", None)
        if label is not None:
            label.setText(mode.value)
        self._logger_refresh_status()

    def _logger_selected_measurements(self) -> tuple[int, ...]:
        return tuple(slot for slot, check in self.logger_measurement_checks.items() if check.isChecked())

    def _logger_config(self) -> LoggerConfig:
        mode = self._logger_mode()
        return LoggerConfig(
            mode=mode,
            interval_s=float(self.logger_interval.value()),
            waveform_sources=self._logger_selected_sources() if mode is LoggerMode.WAVEFORM else (),
            measurement_slots=self._logger_selected_measurements() if mode is LoggerMode.MEASUREMENTS else (),
        )

    def _open_logger_output(self, config: LoggerConfig) -> LoggerOutputSession:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        root = Path(self.output_folder.text()).expanduser() / "logger"
        return LoggerOutputSession(
            root,
            self._selected_output_format(),
            mode=config.mode,
            measurement_slots=config.measurement_slots,
            run_metadata={
                "mode": config.mode.value,
                "waveform_sources": list(config.waveform_sources),
                "measurement_slots": list(config.measurement_slots),
                "encoding": config.encoding,
                "sample_width": config.sample_width,
            },
        )

    def _logger_refresh_status(self) -> None:
        super()._logger_refresh_status()
        editable = not self._logger_active() and not bool(getattr(self, "_operation_active", False))
        combo = getattr(self, "logger_mode_combo", None)
        if combo is not None:
            combo.setEnabled(editable)
        for check in getattr(self, "logger_measurement_checks", {}).values():
            check.setEnabled(editable)
        label = getattr(self, "logger_mode_label", None)
        if label is not None:
            label.setText(self._logger_mode().value)


__all__ = ["QtScopeWindow"]
