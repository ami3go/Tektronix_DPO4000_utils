from __future__ import annotations

import json
from pathlib import Path

import pytest

from dpo4000_utils.logger.models import LoggerConfig
from dpo4000_utils.logger.profiles import (
    LoggerProfile,
    LoggerProfileError,
    load_logger_profile,
    safe_profile_filename,
    save_logger_profile,
    validate_logger_profile_config,
)


def _config(tmp_path: Path) -> dict:
    return {
        "mode": "Mixed record",
        "interval_s": 0.5,
        "waveform_sources": ["CH1", "MATH"],
        "measurement_slots": [1, 2],
        "bus_slots": [],
        "encoding": "RIBINARY",
        "sample_width": 2,
        "point_count": None,
        "output_format": "Binary DPO4LOG",
        "output_root": str(tmp_path / "logger-data"),
        "keep_session": True,
        "rotation": {
            "max_bytes": 1_000_000_000,
            "max_duration_s": 3600.0,
            "max_records": 1000,
            "daily_utc": False,
        },
        "retention": {
            "keep_last_events": 100,
            "max_bytes": 50_000_000_000,
            "max_age_s": 30 * 86400.0,
            "min_free_bytes": 2_000_000_000,
        },
        "recovery": {
            "enabled": True,
            "max_retries": 2,
            "retry_delay_s": 1.0,
            "max_consecutive_failures": 5,
        },
        "buffer": {
            "max_records": 8,
            "max_bytes": 256 * 1024 * 1024,
            "stop_after_overflows": 5,
        },
    }


def test_logger_profile_round_trip(tmp_path: Path) -> None:
    config = _config(tmp_path)
    target = tmp_path / "profiles" / "burn-in.json"
    save_logger_profile(target, LoggerProfile("Burn in", config))

    loaded = load_logger_profile(target)

    assert loaded.name == "Burn in"
    assert dict(loaded.config) == validate_logger_profile_config(config)
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1


def test_logger_profile_rejects_unknown_top_level_and_nested_fields(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config["runtime_state"] = "Running"
    with pytest.raises(LoggerProfileError, match="Unsupported Logger profile field"):
        validate_logger_profile_config(config)

    config = _config(tmp_path)
    config["buffer"]["mystery"] = 123
    with pytest.raises(LoggerProfileError, match="unsupported buffer field"):
        validate_logger_profile_config(config)


def test_logger_profile_rejects_sources_ignored_by_selected_mode(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.update(
        mode="Measurements",
        waveform_sources=["CH1"],
        measurement_slots=[1],
        bus_slots=[],
    )
    with pytest.raises(LoggerProfileError, match="Measurements mode may contain MEAS slots only"):
        validate_logger_profile_config(config)

    config = _config(tmp_path)
    config.update(
        mode="Waveform records",
        waveform_sources=["CH1"],
        measurement_slots=[1],
        bus_slots=[],
    )
    with pytest.raises(LoggerProfileError, match="Waveform mode may contain waveform sources only"):
        validate_logger_profile_config(config)


def test_logger_profile_rejects_non_finite_numbers(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config["interval_s"] = float("nan")
    with pytest.raises(LoggerProfileError, match="non-finite"):
        validate_logger_profile_config(config)


def test_logger_config_validates_transfer_settings_before_capture() -> None:
    with pytest.raises(ValueError):
        LoggerConfig(encoding="NOT-A-WAVEFORM-ENCODING")
    with pytest.raises(ValueError):
        LoggerConfig(sample_width=3)


def test_profile_file_contains_configuration_only(tmp_path: Path) -> None:
    target = tmp_path / "profile.json"
    save_logger_profile(target, LoggerProfile("Config only", _config(tmp_path)))
    text = target.read_text(encoding="utf-8")
    for transient in (
        "records_written",
        "queue_depth",
        "writer_state",
        "started_monotonic",
        "Running",
        "Paused",
    ):
        assert transient not in text


def test_safe_profile_filename_is_bounded_and_sanitized() -> None:
    filename = safe_profile_filename("../../Long burn-in / profile")
    assert filename.endswith(".json")
    assert "/" not in filename
    assert ".." not in filename
    assert len(filename) <= 85


def test_logger_profile_gui_has_no_direct_scope_transport_or_autostart() -> None:
    source = (
        Path(__file__).parents[1]
        / "dpo4000_utils"
        / "gui_qt"
        / "logger_profiles_window.py"
    ).read_text(encoding="utf-8").lower()
    assert "pyvisa" not in source
    assert "resource_manager" not in source
    assert "curve?" not in source
    assert "acquire:" not in source
    assert "self.start_logger()" not in source
