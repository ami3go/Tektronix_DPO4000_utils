"""Reviewed A10 profile application with transactional preflight validation."""

from __future__ import annotations

import math

from .automation_profiles_window import (
    _FILE_WIDGET_NAMES,
    _PROFILE_WIDGET_NAMES,
    QtScopeWindow as AutomationA10QtScopeWindow,
)
from .automation_window import FILE_PAGE_INDEX


def _preflight_widget_value(name: str, widget, value) -> None:
    if hasattr(widget, "isChecked") and hasattr(widget, "setChecked"):
        if not isinstance(value, bool):
            raise ValueError(f"Profile field {name} must be boolean.")
        return
    if hasattr(widget, "value") and hasattr(widget, "setValue"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Profile field {name} must be numeric.")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError(f"Profile field {name} must be finite.")
        if hasattr(widget, "minimum") and numeric < float(widget.minimum()):
            raise ValueError(f"Profile field {name} is below the supported minimum.")
        if hasattr(widget, "maximum") and numeric > float(widget.maximum()):
            raise ValueError(f"Profile field {name} exceeds the supported maximum.")
        return
    if hasattr(widget, "currentText") and hasattr(widget, "setCurrentText"):
        if not isinstance(value, str):
            raise ValueError(f"Profile field {name} must be text.")
        if hasattr(widget, "findText") and hasattr(widget, "isEditable"):
            if widget.findText(value) < 0 and not widget.isEditable():
                raise ValueError(f"Profile field {name} has unsupported value: {value!r}.")
        return
    if hasattr(widget, "text") and hasattr(widget, "setText"):
        if not isinstance(value, str):
            raise ValueError(f"Profile field {name} must be text.")
        return
    raise ValueError(f"Profile field {name} targets an unsupported widget type.")


class QtScopeWindow(AutomationA10QtScopeWindow):
    """A10 window that validates the complete document before mutating widgets."""

    def _preflight_automation_profile_config(self, config: dict) -> None:
        if not self._automation_profile_idle():
            raise RuntimeError("Stop Automation before loading a profile.")
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        mode = str(config.get("mode", "")).strip()
        if not mode or self.automation_mode_combo.findText(mode) < 0:
            raise ValueError(f"Automation mode is not available in this build: {mode!r}")
        widgets = config.get("widgets", {})
        file_config = config.get("file", {})
        slots = config.get("measurement_slots", {})
        if not isinstance(widgets, dict) or not isinstance(file_config, dict) or not isinstance(slots, dict):
            raise ValueError("Automation profile sections must be JSON objects.")
        for name, value in widgets.items():
            if name not in _PROFILE_WIDGET_NAMES:
                raise ValueError(f"Unsupported Automation profile field: {name}")
            widget = getattr(self, name, None)
            if widget is None:
                raise ValueError(f"Automation profile field is unavailable in this build: {name}")
            _preflight_widget_value(name, widget, value)
        for raw_slot, value in slots.items():
            try:
                slot = int(raw_slot)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid measurement slot key: {raw_slot!r}") from exc
            checkbox = getattr(self, "automation_measurement_slots", {}).get(slot)
            if checkbox is None or not isinstance(value, bool):
                raise ValueError(f"Invalid Automation profile measurement slot: MEAS{slot}")
        for name, value in file_config.items():
            if name not in _FILE_WIDGET_NAMES:
                raise ValueError(f"Unsupported File profile field: {name}")
            widget = getattr(self, name, None)
            if widget is None:
                raise ValueError(f"File profile field is unavailable in this build: {name}")
            _preflight_widget_value(name, widget, value)

    def _apply_automation_profile_config(self, config: dict) -> None:
        self._preflight_automation_profile_config(config)
        super()._apply_automation_profile_config(config)


__all__ = ["QtScopeWindow"]
