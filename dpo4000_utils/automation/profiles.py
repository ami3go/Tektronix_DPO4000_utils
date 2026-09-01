"""Versioned Automation profile persistence."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

AUTOMATION_PROFILE_SCHEMA_VERSION = 1
_FORBIDDEN_TRANSIENT_KEYS = {
    "state",
    "statistics",
    "started_at",
    "ended_at",
    "elapsed_s",
    "last_error",
    "last_file",
    "active",
    "busy",
    "generation",
    "attempted",
    "succeeded",
    "failed",
    "skipped",
}


class AutomationProfileError(ValueError):
    """Raised when an Automation profile is malformed or unsafe to apply."""


@dataclass(frozen=True)
class AutomationProfile:
    """One validated schema-versioned Automation configuration snapshot."""

    name: str
    config: dict[str, Any]
    schema_version: int = AUTOMATION_PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not name:
            raise AutomationProfileError("Automation profile name must not be empty.")
        if int(self.schema_version) != AUTOMATION_PROFILE_SCHEMA_VERSION:
            raise AutomationProfileError(
                f"Unsupported Automation profile schema version: {self.schema_version!r}."
            )
        config = validate_automation_profile_config(self.config)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "config", config)
        object.__setattr__(self, "schema_version", AUTOMATION_PROFILE_SCHEMA_VERSION)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "config": self.config,
        }


def _validate_json_value(value: Any, *, path: str = "config") -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, list):
        return [_validate_json_value(item, path=f"{path}[]") for item in value]
    if isinstance(value, tuple):
        return [_validate_json_value(item, path=f"{path}[]") for item in value]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            text = str(key).strip()
            if not text:
                raise AutomationProfileError(f"Empty key is not allowed in {path}.")
            if text.lower() in _FORBIDDEN_TRANSIENT_KEYS:
                raise AutomationProfileError(
                    f"Transient runtime key {text!r} must not be stored in Automation profiles."
                )
            result[text] = _validate_json_value(item, path=f"{path}.{text}")
        return result
    raise AutomationProfileError(
        f"Unsupported value type in Automation profile at {path}: {type(value).__name__}."
    )


def validate_automation_profile_config(config: Mapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
    """Validate a profile config and return a JSON-safe deep copy."""
    if not isinstance(config, Mapping):
        raise AutomationProfileError("Automation profile config must be a JSON object.")
    validated = _validate_json_value(config)
    assert isinstance(validated, dict)
    mode = str(validated.get("mode", "")).strip()
    if not mode:
        raise AutomationProfileError("Automation profile config requires a mode.")
    return validated


def save_automation_profile(path: str | Path, profile: AutomationProfile) -> Path:
    """Atomically save one profile JSON file."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(profile.to_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise AutomationProfileError(f"Could not save Automation profile: {exc}") from exc
    return target


def load_automation_profile(path: str | Path) -> AutomationProfile:
    """Load and validate one profile JSON file."""
    target = Path(path).expanduser()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AutomationProfileError(f"Could not load Automation profile: {exc}") from exc
    if not isinstance(payload, dict):
        raise AutomationProfileError("Automation profile document must be a JSON object.")
    version = payload.get("schema_version")
    if version != AUTOMATION_PROFILE_SCHEMA_VERSION:
        raise AutomationProfileError(f"Unsupported Automation profile schema version: {version!r}.")
    return AutomationProfile(
        name=str(payload.get("name", "")),
        config=payload.get("config", {}),
        schema_version=int(version),
    )


__all__ = [
    "AUTOMATION_PROFILE_SCHEMA_VERSION",
    "AutomationProfile",
    "AutomationProfileError",
    "load_automation_profile",
    "save_automation_profile",
    "validate_automation_profile_config",
]
