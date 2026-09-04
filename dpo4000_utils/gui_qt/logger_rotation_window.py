"""Logger L8 complete-record file rotation."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QFormLayout, QLabel, QSpinBox

from ..logger.models import LoggerConfig
from ..logger.output import LoggerOutputSession
from ..logger.rotation import RotationPolicy
from .logger_mixed_window import QtScopeWindow as LoggerL7QtScopeWindow
from .logger_page_layout import FILE_PAGE_INDEX


class QtScopeWindow(LoggerL7QtScopeWindow):
    """L7 Logger extended with size/duration/count/daily segment rotation."""

    def _build_logger_output_card(self):
        card = super()._build_logger_output_card()
        form = card.layout()
        if not isinstance(form, QFormLayout):
            return card

        self.logger_rotate_size_enabled = QCheckBox("Rotate by size")
        self.logger_rotate_size_enabled.setChecked(True)
        self.logger_rotate_size_gb = QDoubleSpinBox()
        self.logger_rotate_size_gb.setRange(0.01, 1024.0)
        self.logger_rotate_size_gb.setDecimals(2)
        self.logger_rotate_size_gb.setValue(1.0)
        self.logger_rotate_size_gb.setSuffix(" GB")

        self.logger_rotate_duration_enabled = QCheckBox("Rotate by duration")
        self.logger_rotate_duration_enabled.setChecked(True)
        self.logger_rotate_duration_min = QDoubleSpinBox()
        self.logger_rotate_duration_min.setRange(0.1, 10080.0)
        self.logger_rotate_duration_min.setDecimals(1)
        self.logger_rotate_duration_min.setValue(60.0)
        self.logger_rotate_duration_min.setSuffix(" min")

        self.logger_rotate_count_enabled = QCheckBox("Rotate by record count")
        self.logger_rotate_count = QSpinBox()
        self.logger_rotate_count.setRange(1, 10_000_000)
        self.logger_rotate_count.setValue(1000)
        self.logger_rotate_daily_utc = QCheckBox("Rotate at UTC date boundary")

        form.addRow(self.logger_rotate_size_enabled, self.logger_rotate_size_gb)
        form.addRow(self.logger_rotate_duration_enabled, self.logger_rotate_duration_min)
        form.addRow(self.logger_rotate_count_enabled, self.logger_rotate_count)
        form.addRow(self.logger_rotate_daily_utc)
        return card

    def _build_logger_health_card(self):
        card = super()._build_logger_health_card()
        form = card.layout()
        if isinstance(form, QFormLayout):
            self.logger_segment_label = QLabel("0")
            self.logger_rotation_count_label = QLabel("0")
            self.logger_rotation_reason_label = QLabel("--")
            form.addRow("Current segment", self.logger_segment_label)
            form.addRow("Rotations", self.logger_rotation_count_label)
            form.addRow("Last rotation", self.logger_rotation_reason_label)
        return card

    def _selected_rotation_policy(self) -> RotationPolicy:
        max_bytes = None
        if self.logger_rotate_size_enabled.isChecked():
            max_bytes = int(float(self.logger_rotate_size_gb.value()) * 1_000_000_000)
        max_duration_s = None
        if self.logger_rotate_duration_enabled.isChecked():
            max_duration_s = float(self.logger_rotate_duration_min.value()) * 60.0
        max_records = None
        if self.logger_rotate_count_enabled.isChecked():
            max_records = int(self.logger_rotate_count.value())
        return RotationPolicy(
            max_bytes=max_bytes,
            max_duration_s=max_duration_s,
            max_records=max_records,
            daily_utc=self.logger_rotate_daily_utc.isChecked(),
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
                "bus_slots": list(config.bus_slots),
                "encoding": config.encoding,
                "sample_width": config.sample_width,
            },
            rotation_policy=self._selected_rotation_policy(),
        )

    def _logger_refresh_status(self) -> None:
        super()._logger_refresh_status()
        output = getattr(self, "_logger_output_session", None)
        segment = output.segment_index if output is not None else 0
        rotations = output.rotation_count if output is not None else 0
        reason = output.last_rotation_reason if output is not None else ""
        segment_label = getattr(self, "logger_segment_label", None)
        rotation_label = getattr(self, "logger_rotation_count_label", None)
        reason_label = getattr(self, "logger_rotation_reason_label", None)
        if segment_label is not None:
            segment_label.setText(str(segment))
        if rotation_label is not None:
            rotation_label.setText(str(rotations))
        if reason_label is not None:
            reason_label.setText(reason or "--")

        editable = not self._logger_active() and not bool(
            getattr(self, "_operation_active", False)
        )
        controls = (
            "logger_rotate_size_enabled",
            "logger_rotate_size_gb",
            "logger_rotate_duration_enabled",
            "logger_rotate_duration_min",
            "logger_rotate_count_enabled",
            "logger_rotate_count",
            "logger_rotate_daily_utc",
        )
        for name in controls:
            control = getattr(self, name, None)
            if control is not None:
                control.setEnabled(editable)


__all__ = ["QtScopeWindow"]
