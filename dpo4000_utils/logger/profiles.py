"""Versioned Logger configuration profiles."""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..automation.recovery import RecoveryPolicy
from .buffering import BufferPolicy
from .models import LoggerConfig, LoggerMode, LoggerOutputFormat
from .retention import LoggerRetentionPolicy
from .rotation import RotationPolicy

LOGGER_PROFILE_SCHEMA_VERSION = 1
_PROFILE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_ALLOWED_CONFIG_KEYS = {
    "mode",
    "interval_s",
    "waveform_sources",
    "measurement_slots",
    "bus_slots",
    "encoding",
    "sample_width",
    "point_count",
    "output_format",
    "output_root",
    "keep_session",
    "rotation",
    "retention",
    "recovery",
    "buffer",
}
_ALLOWED_ROOT_KEYS = {"schema_version", "name", "config"}
_ALLOWED_SECTION_KEYS = {
    "rotation": {"max_bytes", "max_duration_s", "max_records", "daily_utc"},
    "retention": {"keep_last_events", "max_bytes", "max_age_s", "min_free_bytes"},
    "recovery": {"enabled", "max_retries", "retry_delay_s", "max_consecutive_failures"},
    "buffer": {"max_records", "max_bytes", "stop_after_overflows"},
}


class LoggerProfileError(RuntimeError):
    """Raised for invalid, unsupported, or unreadable Logger profiles."""


@dataclass(frozen=True)
class LoggerProfile:
    name: str
    config: Mapping[str, Any]
    schema_version: int = LOGGER_PROFILE_SCHEMA_VERSION


def safe_profile_filename(name: str) -> str:
    text = _PROFILE_NAME_RE.sub("_", str(name).strip()).strip("._")
    return (text or "logger_profile")[:80] + ".json"


def _validate_json_value(value: Any, path: str = "config") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise LoggerProfileError(f"{path} contains a non-finite number.")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise LoggerProfileError(f"{path} object keys must be strings.")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise LoggerProfileError(
        f"{path} contains unsupported value type {type(value).__name__}."
    )


def _mapping_section(candidate: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = candidate.get(name, {}) or {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    unknown = sorted(set(value) - _ALLOWED_SECTION_KEYS[name])
    if unknown:
        raise ValueError(f"unsupported {name} field(s): {', '.join(unknown)}")
    return value


def validate_logger_profile_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Validate all sections before UI mutation and return normalized JSON-safe data."""
    if not isinstance(config, Mapping):
        raise LoggerProfileError("Logger profile config must be an object.")
    candidate = dict(config)
    unknown = sorted(set(candidate) - _ALLOWED_CONFIG_KEYS)
    if unknown:
        raise LoggerProfileError(
            "Unsupported Logger profile field(s): " + ", ".join(unknown)
        )
    _validate_json_value(candidate)

    try:
        mode = LoggerMode(candidate.get("mode", LoggerMode.WAVEFORM.value))
        default_sources = ("CH1",) if mode is LoggerMode.WAVEFORM else ()
        core = LoggerConfig(
            mode=mode,
            interval_s=candidate.get("interval_s", 1.0),
            waveform_sources=tuple(candidate.get("waveform_sources", default_sources)),
            measurement_slots=tuple(candidate.get("measurement_slots", ())),
            bus_slots=tuple(candidate.get("bus_slots", ())),
            encoding=candidate.get("encoding", "RIBINARY"),
            sample_width=candidate.get("sample_width", 2),
            point_count=candidate.get("point_count"),
        )
        output_format = LoggerOutputFormat(
            candidate.get("output_format", LoggerOutputFormat.BINARY.value)
        )

        rotation_raw = _mapping_section(candidate, "rotation")
        rotation = RotationPolicy(
            max_bytes=rotation_raw.get("max_bytes", 1_000_000_000),
            max_duration_s=rotation_raw.get("max_duration_s", 3600.0),
            max_records=rotation_raw.get("max_records"),
            daily_utc=rotation_raw.get("daily_utc", False),
        )

        retention_raw = _mapping_section(candidate, "retention")
        retention = LoggerRetentionPolicy(
            keep_last_events=retention_raw.get("keep_last_events"),
            max_bytes=retention_raw.get("max_bytes", 50_000_000_000),
            max_age_s=retention_raw.get("max_age_s"),
            min_free_bytes=retention_raw.get("min_free_bytes", 2_000_000_000),
        )

        recovery_raw = _mapping_section(candidate, "recovery")
        recovery = RecoveryPolicy(
            enabled=recovery_raw.get("enabled", True),
            max_retries=recovery_raw.get("max_retries", 2),
            retry_delay_s=recovery_raw.get("retry_delay_s", 1.0),
            max_consecutive_failures=recovery_raw.get("max_consecutive_failures", 5),
        )

        buffer_raw = _mapping_section(candidate, "buffer")
        buffer_policy = BufferPolicy(
            max_records=buffer_raw.get("max_records", 8),
            max_bytes=buffer_raw.get("max_bytes", 256 * 1024 * 1024),
            stop_after_overflows=buffer_raw.get("stop_after_overflows", 5),
        )
    except (TypeError, ValueError) as exc:
        raise LoggerProfileError(f"Invalid Logger profile: {exc}") from exc

    output_root_raw = candidate.get("output_root", "")
    if not isinstance(output_root_raw, str):
        raise LoggerProfileError("Logger profile output_root must be a string.")
    output_root = output_root_raw.strip()
    if not output_root:
        raise LoggerProfileError("Logger profile output_root must not be empty.")
    if "\x00" in output_root:
        raise LoggerProfileError("Logger profile output_root contains a NUL character.")

    keep_session = candidate.get("keep_session", True)
    if not isinstance(keep_session, bool):
        raise LoggerProfileError("Logger profile keep_session must be boolean.")

    return {
        "mode": core.mode.value,
        "interval_s": core.interval_s,
        "waveform_sources": list(core.waveform_sources),
        "measurement_slots": list(core.measurement_slots),
        "bus_slots": list(core.bus_slots),
        "encoding": core.encoding,
        "sample_width": core.sample_width,
        "point_count": core.point_count,
        "output_format": output_format.value,
        "output_root": output_root,
        "keep_session": keep_session,
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


def save_logger_profile(path: str | Path, profile: LoggerProfile) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized = validate_logger_profile_config(profile.config)
    payload = {
        "schema_version": LOGGER_PROFILE_SCHEMA_VERSION,
        "name": str(profile.name).strip() or "Logger profile",
        "config": normalized,
    }
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise LoggerProfileError(f"Could not save Logger profile: {exc}") from exc
    return target


def load_logger_profile(path: str | Path) -> LoggerProfile:
    source = Path(path).expanduser()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LoggerProfileError(f"Could not load Logger profile: {exc}") from exc
    if not isinstance(payload, dict):
        raise LoggerProfileError("Logger profile root must be an object.")
    unknown = sorted(set(payload) - _ALLOWED_ROOT_KEYS)
    if unknown:
        raise LoggerProfileError(
            "Unsupported Logger profile root field(s): " + ", ".join(unknown)
        )
    if payload.get("schema_version") != LOGGER_PROFILE_SCHEMA_VERSION:
        raise LoggerProfileError("Unsupported Logger profile schema version.")
    name = str(payload.get("name", "")).strip() or source.stem
    config = validate_logger_profile_config(payload.get("config", {}))
    return LoggerProfile(name=name, config=config)


__all__ = [
    "LOGGER_PROFILE_SCHEMA_VERSION",
    "LoggerProfile",
    "LoggerProfileError",
    "load_logger_profile",
    "safe_profile_filename",
    "save_logger_profile",
    "validate_logger_profile_config",
]
