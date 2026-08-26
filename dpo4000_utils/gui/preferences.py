"""Persistent user preferences for the PySide6 DPO4000 Desk application."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

APP_CONFIG_DIR_NAME = "DPO4000Utils"
PREFERENCES_FILENAME = "gui_preferences.json"


@dataclass(slots=True)
class GuiPreferences:
    """Serializable desktop UI preference state.

    Hardware state is intentionally not persisted here; this file stores only
    last-used application preferences.
    """

    connection_mode: str = "visa"
    visa_resource: str = "USB0::0x0699::0x0401::C011280::INSTR"
    ethernet_host: str = ""
    ethernet_port: str = "4000"
    ethernet_protocol: str = "VXI-11 / INSTR"
    timeout_ms: str = "20000"
    output_folder: str = "scope_gui_output"
    png_prefix: str = "scope_"
    png_base: str = "screen"
    png_add_timestamp: bool = True
    csv_prefix: str = "scope_"
    csv_base: str = "waveform"
    csv_add_timestamp: bool = True
    settings_prefix: str = "dpo4054_"
    settings_base: str = "setup"
    settings_add_timestamp: bool = True
    restore_wait_opc: bool = False
    rearm_after_image: bool = True
    trigger_channel_after_image: str = ""
    trigger_setup_channel: str = "1"
    trigger_level: str = "1.0"
    trigger_set_source: bool = True

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "GuiPreferences":
        """Build preferences from a possibly partial or stale JSON mapping."""
        defaults = cls()
        if not isinstance(data, dict):
            return defaults

        allowed = {field.name: field for field in fields(cls)}
        values: dict[str, Any] = asdict(defaults)

        for key, value in data.items():
            if key not in allowed:
                continue
            current_default = values[key]
            if isinstance(current_default, bool):
                values[key] = _coerce_bool(value, current_default)
            else:
                values[key] = str(value) if value is not None else current_default

        return cls(**values)

    def to_mapping(self) -> dict[str, Any]:
        """Return JSON-serializable preferences."""
        return asdict(self)


def _coerce_bool(value: Any, default: bool) -> bool:
    """Parse relaxed bool-like values from old or hand-edited config files."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off"}:
            return False
    return default


def default_preferences_dir(app_name: str = APP_CONFIG_DIR_NAME) -> Path:
    """Return the platform-appropriate preferences directory."""
    if os.name == "nt":
        root = os.environ.get("APPDATA")
        if root:
            return Path(root) / app_name
        return Path.home() / "AppData" / "Roaming" / app_name

    if os.sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name

    root = os.environ.get("XDG_CONFIG_HOME")
    if root:
        return Path(root) / app_name
    return Path.home() / ".config" / app_name


def default_preferences_path(app_name: str = APP_CONFIG_DIR_NAME) -> Path:
    """Return the default GUI preferences JSON path."""
    return default_preferences_dir(app_name) / PREFERENCES_FILENAME


def load_preferences(path: str | Path | None = None) -> GuiPreferences:
    """Load GUI preferences, falling back to defaults on missing/invalid files."""
    preferences_path = Path(path) if path is not None else default_preferences_path()
    try:
        data = json.loads(preferences_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return GuiPreferences()
    except Exception:
        return GuiPreferences()
    return GuiPreferences.from_mapping(data)


def save_preferences(preferences: GuiPreferences, path: str | Path | None = None) -> Path:
    """Save GUI preferences and return the written path."""
    preferences_path = Path(path) if path is not None else default_preferences_path()
    preferences_path.parent.mkdir(parents=True, exist_ok=True)
    preferences_path.write_text(
        json.dumps(preferences.to_mapping(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return preferences_path
