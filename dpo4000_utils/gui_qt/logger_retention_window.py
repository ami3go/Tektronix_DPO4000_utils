"""Logger L9 safe retention and minimum-free-space guard."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QFormLayout, QLabel, QSpinBox

from ..logger.models import LoggerState
from ..logger.retention import (
    LoggerRetentionError,
    LoggerRetentionManager,
    LoggerRetentionPolicy,
)
from .logger_page_layout import FILE_PAGE_INDEX
from .logger_rotation_window import QtScopeWindow as LoggerL8QtScopeWindow


class QtScopeWindow(LoggerL8QtScopeWindow):
    """L8 Logger extended with ownership-based retention."""

    def __init__(self, *args, **kwargs) -> None:
        self._logger_retention_manager: LoggerRetentionManager | None = None
        self._logger_retention_last_rotation = 0
        super().__init__(*args, **kwargs)

    def _build_logger_output_card(self):
        card = super()._build_logger_output_card()
        form = card.layout()
        if not isinstance(form, QFormLayout):
            return card

        self.logger_keep_segments_enabled = QCheckBox("Keep only last segments")
        self.logger_keep_segments = QSpinBox()
        self.logger_keep_segments.setRange(1, 1_000_000)
        self.logger_keep_segments.setValue(100)

        self.logger_max_storage_enabled = QCheckBox("Limit Logger storage")
        self.logger_max_storage_enabled.setChecked(True)
        self.logger_max_storage_gb = QDoubleSpinBox()
        self.logger_max_storage_gb.setRange(0.1, 100_000.0)
        self.logger_max_storage_gb.setDecimals(1)
        self.logger_max_storage_gb.setValue(50.0)
        self.logger_max_storage_gb.setSuffix(" GB")

        self.logger_max_age_enabled = QCheckBox("Delete older segments")
        self.logger_max_age_days = QDoubleSpinBox()
        self.logger_max_age_days.setRange(0.1, 3650.0)
        self.logger_max_age_days.setDecimals(1)
        self.logger_max_age_days.setValue(30.0)
        self.logger_max_age_days.setSuffix(" days")

        self.logger_min_free_enabled = QCheckBox("Minimum free disk guard")
        self.logger_min_free_enabled.setChecked(True)
        self.logger_min_free_gb = QDoubleSpinBox()
        self.logger_min_free_gb.setRange(0.1, 10_000.0)
        self.logger_min_free_gb.setDecimals(1)
        self.logger_min_free_gb.setValue(2.0)
        self.logger_min_free_gb.setSuffix(" GB")

        form.addRow(self.logger_keep_segments_enabled, self.logger_keep_segments)
        form.addRow(self.logger_max_storage_enabled, self.logger_max_storage_gb)
        form.addRow(self.logger_max_age_enabled, self.logger_max_age_days)
        form.addRow(self.logger_min_free_enabled, self.logger_min_free_gb)
        return card

    def _build_logger_health_card(self):
        card = super()._build_logger_health_card()
        form = card.layout()
        if isinstance(form, QFormLayout):
            self.logger_retention_deleted_label = QLabel("0")
            self.logger_retention_reclaimed_label = QLabel("0.0 MB")
            self.logger_free_disk_label = QLabel("--")
            form.addRow("Retention deleted", self.logger_retention_deleted_label)
            form.addRow("Retention reclaimed", self.logger_retention_reclaimed_label)
            form.addRow("Free disk", self.logger_free_disk_label)
        return card

    def _selected_logger_retention_policy(self) -> LoggerRetentionPolicy:
        keep_last = (
            int(self.logger_keep_segments.value())
            if self.logger_keep_segments_enabled.isChecked()
            else None
        )
        max_bytes = (
            int(float(self.logger_max_storage_gb.value()) * 1_000_000_000)
            if self.logger_max_storage_enabled.isChecked()
            else None
        )
        max_age_s = (
            float(self.logger_max_age_days.value()) * 86400.0
            if self.logger_max_age_enabled.isChecked()
            else None
        )
        min_free_bytes = (
            int(float(self.logger_min_free_gb.value()) * 1_000_000_000)
            if self.logger_min_free_enabled.isChecked()
            else None
        )
        return LoggerRetentionPolicy(
            keep_last_events=keep_last,
            max_bytes=max_bytes,
            max_age_s=max_age_s,
            min_free_bytes=min_free_bytes,
        )

    def _logger_root(self) -> Path:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        return (Path(self.output_folder.text()).expanduser() / "logger").resolve()

    def start_logger(self) -> None:
        if self._logger_active():
            return
        try:
            manager = LoggerRetentionManager(
                self._logger_root(),
                self._selected_logger_retention_policy(),
            )
            manager.apply()
        except Exception as exc:  # noqa: BLE001 - retention safety must block start.
            self._message("Logger retention", str(exc), error=True)
            return

        self._logger_retention_manager = manager
        self._logger_retention_last_rotation = 0
        super().start_logger()
        if not self._logger_active():
            self._logger_retention_manager = None
        self._logger_refresh_status()

    def _apply_completed_logger_segments(self, output) -> None:
        manager = self._logger_retention_manager
        if manager is None:
            return
        manager.register_closed_segments(output.completed_segments)
        manager.apply()
        self._logger_retention_last_rotation = output.rotation_count

    def _logger_tick(self) -> None:
        output = getattr(self, "_logger_output_session", None)
        super()._logger_tick()
        if self._logger_state is LoggerState.FAILED:
            return
        active_output = getattr(self, "_logger_output_session", None) or output
        if active_output is None:
            return
        if active_output.rotation_count <= self._logger_retention_last_rotation:
            return
        try:
            self._apply_completed_logger_segments(active_output)
        except LoggerRetentionError as exc:
            self._logger_statistics.failed += 1
            self._logger_statistics.last_error = str(exc)
            self._append_log(f"Logger retention failed: {exc}")
            super().stop_logger()
            self._logger_state = LoggerState.FAILED
            self._logger_refresh_status()

    def stop_logger(self) -> None:
        output = getattr(self, "_logger_output_session", None)
        was_active = self._logger_active()
        super().stop_logger()
        if not was_active or output is None or self._logger_state is LoggerState.FAILED:
            return
        try:
            self._apply_completed_logger_segments(output)
        except LoggerRetentionError as exc:
            self._logger_statistics.failed += 1
            self._logger_statistics.last_error = str(exc)
            self._logger_state = LoggerState.FAILED
            self._append_log(f"Logger retention finalization failed: {exc}")
        self._logger_refresh_status()

    def _logger_refresh_status(self) -> None:
        super()._logger_refresh_status()
        manager = self._logger_retention_manager
        stats = manager.statistics if manager is not None else None
        deleted = stats.deleted_segments if stats is not None else 0
        reclaimed = stats.reclaimed_bytes if stats is not None else 0
        deleted_label = getattr(self, "logger_retention_deleted_label", None)
        reclaimed_label = getattr(self, "logger_retention_reclaimed_label", None)
        free_label = getattr(self, "logger_free_disk_label", None)
        if deleted_label is not None:
            deleted_label.setText(str(deleted))
        if reclaimed_label is not None:
            reclaimed_label.setText(f"{reclaimed / 1_000_000:.1f} MB")
        if free_label is not None:
            try:
                free = shutil.disk_usage(self._logger_root()).free
                free_label.setText(f"{free / 1_000_000_000:.2f} GB")
            except Exception:
                free_label.setText("--")

        editable = not self._logger_active() and not bool(
            getattr(self, "_operation_active", False)
        )
        for name in (
            "logger_keep_segments_enabled",
            "logger_keep_segments",
            "logger_max_storage_enabled",
            "logger_max_storage_gb",
            "logger_max_age_enabled",
            "logger_max_age_days",
            "logger_min_free_enabled",
            "logger_min_free_gb",
        ):
            control = getattr(self, name, None)
            if control is not None:
                control.setEnabled(editable)


__all__ = ["QtScopeWindow"]
