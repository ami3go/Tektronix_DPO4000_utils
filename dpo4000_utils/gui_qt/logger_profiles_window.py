"""Logger L12 versioned profile UI."""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QWidget

from ..logger.buffering import BufferSnapshot
from ..logger.profiles import (
    LoggerProfile,
    load_logger_profile,
    safe_profile_filename,
    save_logger_profile,
    validate_logger_profile_config,
)
from .logger_buffer_window import QtScopeWindow as LoggerL11QtScopeWindow
from .logger_page_layout import FILE_PAGE_INDEX


class QtScopeWindow(LoggerL11QtScopeWindow):
    """L11 Logger extended with validated, non-autostart JSON profiles."""

    def __init__(self, *args, **kwargs) -> None:
        self._logger_profile_path: Path | None = None
        self._logger_profile_buttons: list[object] = []
        super().__init__(*args, **kwargs)

    def _build_logger_status_card(self):
        card = super()._build_logger_status_card()
        form = card.layout()
        if not isinstance(form, QFormLayout):
            return card

        self.logger_profile_name = QLineEdit("Default")
        self.logger_profile_name.setPlaceholderText("Profile name")
        name_row = QWidget()
        name_layout = QHBoxLayout(name_row)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(6)
        name_layout.addWidget(self.logger_profile_name, 1)

        buttons_row = QWidget()
        buttons_layout = QHBoxLayout(buttons_row)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(6)
        buttons = (
            self._button("New", self.new_logger_profile),
            self._button("Save", self.save_logger_profile),
            self._button("Save As", self.save_logger_profile_as),
            self._button("Import", self.import_logger_profile),
            self._button("Export", self.export_logger_profile),
        )
        self._logger_profile_buttons = list(buttons)
        for button in buttons:
            buttons_layout.addWidget(button)

        form.insertRow(0, "Profile", name_row)
        form.insertRow(1, buttons_row)
        return card

    def _logger_profile_idle(self) -> bool:
        return (
            not self._logger_active()
            and not self._logger_writer_active()
            and not bool(getattr(self, "_operation_active", False))
        )

    def _collect_logger_profile_config(self) -> dict:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        core = self._logger_config()
        rotation = self._selected_rotation_policy()
        retention = self._selected_logger_retention_policy()
        recovery = self._logger_recovery_policy()
        buffer_policy = self._selected_buffer_policy()
        keep = getattr(self, "keep_session", None)
        if keep is None:
            raise RuntimeError("Keep-session control is unavailable in this build.")
        return {
            "mode": core.mode.value,
            "interval_s": core.interval_s,
            "waveform_sources": list(core.waveform_sources),
            "measurement_slots": list(core.measurement_slots),
            "bus_slots": list(core.bus_slots),
            "encoding": core.encoding,
            "sample_width": core.sample_width,
            "point_count": core.point_count,
            "output_format": self._selected_output_format().value,
            "output_root": str(self.output_folder.text()).strip(),
            "keep_session": bool(keep.isChecked()),
            "rotation": {
                "max_bytes": rotation.max_bytes,
                "max_duration_s": rotation.max_duration_s,
                "max_records": rotation.max_records,
                "daily_utc": rotation.daily_utc,
            },
            "retention": {
                "keep_last_events": retention.keep_last_events,
                "max_bytes": retention.max_bytes,
                "max_age_s": retention.max_age_s,
                "min_free_bytes": retention.min_free_bytes,
            },
            "recovery": {
                "enabled": recovery.enabled,
                "max_retries": recovery.max_retries,
                "retry_delay_s": recovery.retry_delay_s,
                "max_consecutive_failures": recovery.max_consecutive_failures,
            },
            "buffer": {
                "max_records": buffer_policy.max_records,
                "max_bytes": buffer_policy.max_bytes,
                "stop_after_overflows": buffer_policy.stop_after_overflows,
            },
        }

    @staticmethod
    def _ensure_control_value(control, value: float, label: str) -> None:
        minimum = float(control.minimum())
        maximum = float(control.maximum())
        numeric = float(value)
        if numeric < minimum or numeric > maximum:
            raise ValueError(
                f"{label}={numeric:g} is outside this build's supported range "
                f"{minimum:g}..{maximum:g}."
            )
        if hasattr(control, "decimals"):
            represented = round(numeric, int(control.decimals()))
            if not math.isclose(represented, numeric, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError(
                    f"{label}={numeric:g} cannot be represented exactly by this UI."
                )
        elif not numeric.is_integer():
            raise ValueError(
                f"{label}={numeric:g} cannot be represented by this integer control."
            )

    def _preflight_logger_profile_ui(self, config: dict) -> dict:
        if not self._logger_profile_idle():
            raise RuntimeError("Stop Logger before loading a profile.")
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        normalized = validate_logger_profile_config(config)

        mode_combo = getattr(self, "logger_mode_combo", None)
        output_combo = getattr(self, "logger_output_format", None)
        keep = getattr(self, "keep_session", None)
        if mode_combo is None or output_combo is None or keep is None:
            raise ValueError("Required Logger profile controls are unavailable in this build.")
        if mode_combo.findText(normalized["mode"]) < 0:
            raise ValueError(f"Logger mode is unavailable in this build: {normalized['mode']}")
        if output_combo.findText(normalized["output_format"]) < 0:
            raise ValueError(
                f"Logger output format is unavailable in this build: {normalized['output_format']}"
            )

        available_waveforms = set(getattr(self, "logger_channel_checks", {}))
        if getattr(self, "logger_math_check", None) is not None:
            available_waveforms.add("MATH")
        unsupported_sources = sorted(set(normalized["waveform_sources"]) - available_waveforms)
        if unsupported_sources:
            raise ValueError(
                "Logger waveform source(s) unavailable in this UI: "
                + ", ".join(unsupported_sources)
            )
        available_measurements = set(getattr(self, "logger_measurement_checks", {}))
        unsupported_measurements = sorted(
            set(normalized["measurement_slots"]) - available_measurements
        )
        if unsupported_measurements:
            raise ValueError(
                "Logger MEAS slot(s) unavailable in this UI: "
                + ", ".join(f"MEAS{slot}" for slot in unsupported_measurements)
            )
        available_buses = set(getattr(self, "logger_bus_checks", {}))
        unsupported_buses = sorted(set(normalized["bus_slots"]) - available_buses)
        if unsupported_buses:
            raise ValueError(
                "Logger BUS slot(s) unavailable in this UI: "
                + ", ".join(f"BUS{slot}" for slot in unsupported_buses)
            )

        # Transfer controls are not editable in the current Logger UI. Reject
        # incompatible imported profiles instead of silently dropping these values.
        if normalized["encoding"] != "RIBINARY":
            raise ValueError("This Logger UI currently supports profile encoding RIBINARY only.")
        if normalized["sample_width"] != 2:
            raise ValueError("This Logger UI currently supports 2-byte waveform samples only.")
        if normalized["point_count"] is not None:
            raise ValueError("This Logger UI currently profiles full/current record length only.")

        self._ensure_control_value(self.logger_interval, normalized["interval_s"], "interval_s")
        rotation = normalized["rotation"]
        if rotation["max_bytes"] is not None:
            self._ensure_control_value(
                self.logger_rotate_size_gb,
                rotation["max_bytes"] / 1_000_000_000,
                "rotation.max_bytes",
            )
        if rotation["max_duration_s"] is not None:
            self._ensure_control_value(
                self.logger_rotate_duration_min,
                rotation["max_duration_s"] / 60.0,
                "rotation.max_duration_s",
            )
        if rotation["max_records"] is not None:
            self._ensure_control_value(
                self.logger_rotate_count,
                rotation["max_records"],
                "rotation.max_records",
            )

        retention = normalized["retention"]
        if retention["keep_last_events"] is not None:
            self._ensure_control_value(
                self.logger_keep_segments,
                retention["keep_last_events"],
                "retention.keep_last_events",
            )
        if retention["max_bytes"] is not None:
            self._ensure_control_value(
                self.logger_max_storage_gb,
                retention["max_bytes"] / 1_000_000_000,
                "retention.max_bytes",
            )
        if retention["max_age_s"] is not None:
            self._ensure_control_value(
                self.logger_max_age_days,
                retention["max_age_s"] / 86400.0,
                "retention.max_age_s",
            )
        if retention["min_free_bytes"] is not None:
            self._ensure_control_value(
                self.logger_min_free_gb,
                retention["min_free_bytes"] / 1_000_000_000,
                "retention.min_free_bytes",
            )

        recovery = normalized["recovery"]
        self._ensure_control_value(
            self.logger_reconnect_retries,
            recovery["max_retries"],
            "recovery.max_retries",
        )
        self._ensure_control_value(
            self.logger_reconnect_delay,
            recovery["retry_delay_s"],
            "recovery.retry_delay_s",
        )
        self._ensure_control_value(
            self.logger_reconnect_max_failures,
            recovery["max_consecutive_failures"],
            "recovery.max_consecutive_failures",
        )

        buffer_config = normalized["buffer"]
        self._ensure_control_value(
            self.logger_queue_records,
            buffer_config["max_records"],
            "buffer.max_records",
        )
        self._ensure_control_value(
            self.logger_queue_memory_mb,
            buffer_config["max_bytes"] / (1024 * 1024),
            "buffer.max_bytes",
        )
        self._ensure_control_value(
            self.logger_queue_stop_overflows,
            buffer_config["stop_after_overflows"],
            "buffer.stop_after_overflows",
        )
        return normalized

    def _apply_logger_profile_config(self, config: dict) -> None:
        normalized = self._preflight_logger_profile_ui(config)

        self.logger_mode_combo.setCurrentText(normalized["mode"])
        self.logger_interval.setValue(float(normalized["interval_s"]))
        selected_waveforms = set(normalized["waveform_sources"])
        for source, check in self.logger_channel_checks.items():
            check.setChecked(source in selected_waveforms)
        math_check = getattr(self, "logger_math_check", None)
        if math_check is not None:
            math_check.setChecked("MATH" in selected_waveforms)
        selected_measurements = set(normalized["measurement_slots"])
        for slot, check in self.logger_measurement_checks.items():
            check.setChecked(slot in selected_measurements)
        selected_buses = set(normalized["bus_slots"])
        for slot, check in self.logger_bus_checks.items():
            check.setChecked(slot in selected_buses)

        self.logger_output_format.setCurrentText(normalized["output_format"])
        self.output_folder.setText(normalized["output_root"])
        self.keep_session.setChecked(bool(normalized["keep_session"]))

        rotation = normalized["rotation"]
        self.logger_rotate_size_enabled.setChecked(rotation["max_bytes"] is not None)
        if rotation["max_bytes"] is not None:
            self.logger_rotate_size_gb.setValue(rotation["max_bytes"] / 1_000_000_000)
        self.logger_rotate_duration_enabled.setChecked(rotation["max_duration_s"] is not None)
        if rotation["max_duration_s"] is not None:
            self.logger_rotate_duration_min.setValue(rotation["max_duration_s"] / 60.0)
        self.logger_rotate_count_enabled.setChecked(rotation["max_records"] is not None)
        if rotation["max_records"] is not None:
            self.logger_rotate_count.setValue(int(rotation["max_records"]))
        self.logger_rotate_daily_utc.setChecked(bool(rotation["daily_utc"]))

        retention = normalized["retention"]
        self.logger_keep_segments_enabled.setChecked(retention["keep_last_events"] is not None)
        if retention["keep_last_events"] is not None:
            self.logger_keep_segments.setValue(int(retention["keep_last_events"]))
        self.logger_max_storage_enabled.setChecked(retention["max_bytes"] is not None)
        if retention["max_bytes"] is not None:
            self.logger_max_storage_gb.setValue(retention["max_bytes"] / 1_000_000_000)
        self.logger_max_age_enabled.setChecked(retention["max_age_s"] is not None)
        if retention["max_age_s"] is not None:
            self.logger_max_age_days.setValue(retention["max_age_s"] / 86400.0)
        self.logger_min_free_enabled.setChecked(retention["min_free_bytes"] is not None)
        if retention["min_free_bytes"] is not None:
            self.logger_min_free_gb.setValue(retention["min_free_bytes"] / 1_000_000_000)

        recovery = normalized["recovery"]
        self.logger_reconnect_enabled.setChecked(bool(recovery["enabled"]))
        self.logger_reconnect_retries.setValue(int(recovery["max_retries"]))
        self.logger_reconnect_delay.setValue(float(recovery["retry_delay_s"]))
        self.logger_reconnect_max_failures.setValue(int(recovery["max_consecutive_failures"]))

        buffer_config = normalized["buffer"]
        self.logger_queue_records.setValue(int(buffer_config["max_records"]))
        self.logger_queue_memory_mb.setValue(int(buffer_config["max_bytes"] // (1024 * 1024)))
        self.logger_queue_stop_overflows.setValue(int(buffer_config["stop_after_overflows"]))

        # Profiles never restore runtime state. Clear stale run/retention health after
        # changing paths/policies so the next run starts from a clean snapshot.
        self._logger_retention_manager = None
        self._logger_last_writer_snapshot = BufferSnapshot()
        self._logger_last_file = None
        self._logger_writer_error_announced = False
        self._logger_mode_changed()
        self._logger_refresh_status()

    def _logger_profile_default_directory(self) -> Path:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        return Path(self.output_folder.text()).expanduser() / "logger_profiles"

    def new_logger_profile(self) -> None:
        if not self._logger_profile_idle():
            self._message("Logger profile", "Stop Logger before creating a profile.", error=True)
            return
        self._logger_profile_path = None
        self.logger_profile_name.setText("New profile")
        self.statusBar().showMessage("New Logger profile: current settings retained, not started")

    def _save_logger_profile_to(self, path: Path, *, adopt: bool) -> None:
        if not self._logger_profile_idle():
            self._message("Logger profile", "Stop Logger before saving a profile.", error=True)
            return
        try:
            profile = LoggerProfile(
                name=self.logger_profile_name.text().strip() or path.stem,
                config=self._collect_logger_profile_config(),
            )
            saved = save_logger_profile(path, profile)
        except Exception as exc:  # noqa: BLE001 - exact validation/file diagnostic.
            self._message("Logger profile", str(exc), error=True)
            return
        if adopt:
            self._logger_profile_path = saved
            self.logger_profile_name.setText(profile.name)
        self.statusBar().showMessage(f"Logger profile saved: {saved.name}")
        self._append_log(f"Logger profile saved: {saved}")

    def save_logger_profile(self) -> None:
        if self._logger_profile_path is None:
            self.save_logger_profile_as()
            return
        self._save_logger_profile_to(self._logger_profile_path, adopt=True)

    def save_logger_profile_as(self) -> None:
        if not self._logger_profile_idle():
            self._message("Logger profile", "Stop Logger before saving a profile.", error=True)
            return
        default = self._logger_profile_default_directory() / safe_profile_filename(
            self.logger_profile_name.text()
        )
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Save Logger profile",
            str(default),
            "JSON files (*.json);;All files (*.*)",
        )
        if selected:
            self._save_logger_profile_to(Path(selected), adopt=True)

    def export_logger_profile(self) -> None:
        if not self._logger_profile_idle():
            self._message("Logger profile", "Stop Logger before exporting a profile.", error=True)
            return
        default = self._logger_profile_default_directory() / safe_profile_filename(
            self.logger_profile_name.text()
        )
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Export Logger profile",
            str(default),
            "JSON files (*.json);;All files (*.*)",
        )
        if selected:
            self._save_logger_profile_to(Path(selected), adopt=False)

    def import_logger_profile(self) -> None:
        if not self._logger_profile_idle():
            self._message("Logger profile", "Stop Logger before importing a profile.", error=True)
            return
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Import Logger profile",
            str(self._logger_profile_default_directory()),
            "JSON files (*.json);;All files (*.*)",
        )
        if not selected:
            return
        path = Path(selected)
        try:
            profile = load_logger_profile(path)
            self._apply_logger_profile_config(dict(profile.config))
        except Exception as exc:  # noqa: BLE001 - exact validation/file diagnostic.
            self._message("Logger profile", str(exc), error=True)
            return
        self._logger_profile_path = path
        self.logger_profile_name.setText(profile.name)
        self.statusBar().showMessage(f"Logger profile loaded: {profile.name} (not started)")
        self._append_log(f"Logger profile loaded without auto-start: {path}")

    def _logger_refresh_status(self) -> None:
        super()._logger_refresh_status()
        profile_name = getattr(self, "logger_profile_name", None)
        if profile_name is None:
            return
        editable = self._logger_profile_idle()
        profile_name.setEnabled(editable)
        for button in self._logger_profile_buttons:
            button.setEnabled(editable)


__all__ = ["QtScopeWindow"]
