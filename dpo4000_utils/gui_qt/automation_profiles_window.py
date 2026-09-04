"""A10 Automation profile UI and configuration projection."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QLineEdit, QWidget

from ..automation.profiles import AutomationProfile, load_automation_profile, save_automation_profile
from .automation_retention_review_window import QtScopeWindow as AutomationA9ReviewedQtScopeWindow
from .automation_window import FILE_PAGE_INDEX

_PROFILE_WIDGET_NAMES = (
    "automation_interval_value",
    "automation_interval_unit",
    "automation_trigger_poll",
    "automation_trigger_rearm",
    "automation_condition_slot",
    "automation_condition_operator",
    "automation_condition_threshold",
    "automation_condition_high",
    "automation_condition_debounce",
    "automation_condition_cooldown",
    "automation_condition_action",
    "automation_burst_count",
    "automation_burst_delay",
    "automation_burst_action",
    "automation_burst_single",
    "automation_burst_poll",
    "automation_limit_count_enabled",
    "automation_limit_count",
    "automation_limit_duration_enabled",
    "automation_limit_duration",
    "automation_limit_duration_unit",
    "automation_retention_count_enabled",
    "automation_retention_count",
    "automation_retention_size_enabled",
    "automation_retention_size_gb",
    "automation_retention_age_enabled",
    "automation_retention_age_days",
    "automation_retention_free_enabled",
    "automation_retention_free_gb",
)
_FILE_WIDGET_NAMES = (
    "output_folder",
    "png_prefix",
    "png_base",
    "png_timestamp",
    "csv_prefix",
    "csv_base",
    "csv_timestamp",
    "settings_prefix",
    "settings_base",
    "settings_timestamp",
)


def _widget_value(widget):
    if hasattr(widget, "isChecked"):
        return bool(widget.isChecked())
    if hasattr(widget, "value"):
        return widget.value()
    if hasattr(widget, "currentText"):
        return str(widget.currentText())
    if hasattr(widget, "text"):
        return str(widget.text())
    raise TypeError(f"Unsupported profile widget type: {type(widget).__name__}")


def _apply_widget_value(widget, value) -> None:
    if hasattr(widget, "setChecked") and isinstance(value, bool):
        widget.setChecked(value)
        return
    if hasattr(widget, "setValue") and isinstance(value, (int, float)) and not isinstance(value, bool):
        widget.setValue(value)
        return
    if hasattr(widget, "setCurrentText") and isinstance(value, str):
        widget.setCurrentText(value)
        return
    if hasattr(widget, "setText") and isinstance(value, str):
        widget.setText(value)
        return
    raise TypeError(f"Unsupported value {value!r} for profile widget {type(widget).__name__}")


class QtScopeWindow(AutomationA9ReviewedQtScopeWindow):
    """A9 reviewed window extended with validated A10 JSON profiles."""

    def __init__(self, *args, **kwargs) -> None:
        self._automation_profile_path: Path | None = None
        super().__init__(*args, **kwargs)

    def _build_automation_status_card(self):
        card = super()._build_automation_status_card()
        form = card.layout()
        self.automation_profile_name = QLineEdit("Default")
        self.automation_profile_name.setPlaceholderText("Profile name")
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.automation_profile_name, 1)
        layout.addWidget(self._button("Save", self.save_automation_profile), 0)
        layout.addWidget(self._button("Load", self.load_automation_profile), 0)
        layout.addWidget(self._button("Save as", self.save_automation_profile_as), 0)
        if hasattr(form, "addRow"):
            form.addRow("Profile", row)
        return card

    def _automation_profile_idle(self) -> bool:
        return not self._automation_any_active() and not bool(getattr(self, "_operation_active", False))

    def _collect_automation_profile_config(self) -> dict:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        config: dict = {
            "mode": self._automation_mode(),
            "widgets": {},
            "measurement_slots": {},
            "file": {},
        }
        widgets = config["widgets"]
        for name in _PROFILE_WIDGET_NAMES:
            widget = getattr(self, name, None)
            if widget is not None:
                widgets[name] = _widget_value(widget)
        slots = getattr(self, "automation_measurement_slots", {})
        config["measurement_slots"] = {
            str(slot): bool(checkbox.isChecked()) for slot, checkbox in sorted(slots.items())
        }
        file_config = config["file"]
        for name in _FILE_WIDGET_NAMES:
            widget = getattr(self, name, None)
            if widget is not None:
                file_config[name] = _widget_value(widget)
        return config

    def _apply_automation_profile_config(self, config: dict) -> None:
        if not self._automation_profile_idle():
            raise RuntimeError("Stop Automation before loading a profile.")
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        mode = str(config.get("mode", "")).strip()
        if not mode:
            raise ValueError("Automation profile has no mode.")
        index = self.automation_mode_combo.findText(mode)
        if index < 0:
            raise ValueError(f"Automation mode is not available in this build: {mode}")

        widgets = config.get("widgets", {})
        file_config = config.get("file", {})
        slots = config.get("measurement_slots", {})
        if not isinstance(widgets, dict) or not isinstance(file_config, dict) or not isinstance(slots, dict):
            raise ValueError("Automation profile sections must be JSON objects.")

        # Apply the mode first so mode-specific visibility/validation hooks run consistently.
        self.automation_mode_combo.setCurrentIndex(index)
        for name, value in widgets.items():
            if name not in _PROFILE_WIDGET_NAMES:
                raise ValueError(f"Unsupported Automation profile field: {name}")
            widget = getattr(self, name, None)
            if widget is None:
                raise ValueError(f"Automation profile field is unavailable in this build: {name}")
            _apply_widget_value(widget, value)
        for raw_slot, value in slots.items():
            slot = int(raw_slot)
            checkbox = getattr(self, "automation_measurement_slots", {}).get(slot)
            if checkbox is None:
                raise ValueError(f"Measurement slot is unavailable: MEAS{slot}")
            if not isinstance(value, bool):
                raise ValueError(f"Measurement slot MEAS{slot} must be boolean.")
            checkbox.setChecked(value)
        for name, value in file_config.items():
            if name not in _FILE_WIDGET_NAMES:
                raise ValueError(f"Unsupported File profile field: {name}")
            widget = getattr(self, name, None)
            if widget is None:
                raise ValueError(f"File profile field is unavailable in this build: {name}")
            _apply_widget_value(widget, value)

        # Destructive retention is never enabled merely by loading a profile.
        if hasattr(self, "automation_retention_auto"):
            self.automation_retention_auto.setChecked(False)
            self.automation_retention_auto.setEnabled(False)
        self._retention_preview_ack = False
        if hasattr(self, "_retention_preview_root"):
            self._retention_preview_root = None
        self._automation_mode_changed()
        self._automation_refresh_status()

    def _profile_default_directory(self) -> Path:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        root = Path(self.output_folder.text()).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def save_automation_profile_as(self) -> None:
        if not self._automation_profile_idle():
            self._message("Automation profile", "Stop Automation before saving a profile.", error=True)
            return
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Save Automation profile",
            str(self._profile_default_directory() / "automation-profile.json"),
            "JSON files (*.json);;All files (*.*)",
        )
        if not selected:
            return
        self._save_automation_profile_to(Path(selected))

    def save_automation_profile(self) -> None:
        if self._automation_profile_path is None:
            self.save_automation_profile_as()
            return
        self._save_automation_profile_to(self._automation_profile_path)

    def _save_automation_profile_to(self, path: Path) -> None:
        if not self._automation_profile_idle():
            self._message("Automation profile", "Stop Automation before saving a profile.", error=True)
            return
        try:
            profile = AutomationProfile(
                name=self.automation_profile_name.text().strip() or path.stem,
                config=self._collect_automation_profile_config(),
            )
            saved = save_automation_profile(path, profile)
        except Exception as exc:  # noqa: BLE001 - exact validation/file diagnostic.
            self._message("Automation profile", str(exc), error=True)
            return
        self._automation_profile_path = saved
        self.automation_profile_name.setText(profile.name)
        self.statusBar().showMessage(f"Automation profile saved: {saved.name}")
        self._append_log(f"Automation profile saved: {saved}")

    def load_automation_profile(self) -> None:
        if not self._automation_profile_idle():
            self._message("Automation profile", "Stop Automation before loading a profile.", error=True)
            return
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Load Automation profile",
            str(self._profile_default_directory()),
            "JSON files (*.json);;All files (*.*)",
        )
        if not selected:
            return
        path = Path(selected)
        try:
            profile = load_automation_profile(path)
            self._apply_automation_profile_config(profile.config)
        except Exception as exc:  # noqa: BLE001 - exact validation/file diagnostic.
            self._message("Automation profile", str(exc), error=True)
            return
        self._automation_profile_path = path
        self.automation_profile_name.setText(profile.name)
        self.statusBar().showMessage(f"Automation profile loaded: {profile.name} (not started)")
        self._append_log(f"Automation profile loaded without auto-start: {path}")


__all__ = ["QtScopeWindow"]
