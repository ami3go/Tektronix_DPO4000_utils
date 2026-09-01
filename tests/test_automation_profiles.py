from __future__ import annotations

import json
from pathlib import Path

import pytest

from dpo4000_utils.automation.profiles import (
    AUTOMATION_PROFILE_SCHEMA_VERSION,
    AutomationProfile,
    AutomationProfileError,
    load_automation_profile,
    save_automation_profile,
)


def test_a10_profile_round_trip_is_versioned_and_does_not_store_runtime_state(tmp_path: Path) -> None:
    profile = AutomationProfile(
        name="Bench trigger capture",
        config={
            "mode": "Image + CSV on Trigger",
            "widgets": {"automation_trigger_poll": 0.5, "automation_trigger_rearm": True},
            "measurement_slots": {"1": True, "2": False},
            "file": {"output_folder": str(tmp_path)},
        },
    )
    path = save_automation_profile(tmp_path / "profile.json", profile)
    loaded = load_automation_profile(path)
    assert loaded == profile
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == AUTOMATION_PROFILE_SCHEMA_VERSION
    assert "state" not in json.dumps(payload).lower()


def test_a10_profile_rejects_transient_runtime_keys() -> None:
    with pytest.raises(AutomationProfileError, match="Transient runtime key"):
        AutomationProfile(name="bad", config={"mode": "Periodic Image", "state": "Running"})
    with pytest.raises(AutomationProfileError, match="Transient runtime key"):
        AutomationProfile(
            name="bad",
            config={"mode": "Periodic Image", "nested": {"statistics": {"succeeded": 1}}},
        )


def test_a10_profile_rejects_unknown_schema(tmp_path: Path) -> None:
    path = tmp_path / "future.json"
    path.write_text(
        json.dumps({"schema_version": 999, "name": "future", "config": {"mode": "Periodic Image"}}),
        encoding="utf-8",
    )
    with pytest.raises(AutomationProfileError, match="Unsupported"):
        load_automation_profile(path)


def test_a10_gui_load_never_autostarts_and_stays_behind_driver_boundary() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "dpo4000_utils" / "gui_qt" / "automation_profiles_window.py").read_text(
        encoding="utf-8"
    )
    assert "loaded without auto-start" in source
    assert "super().start_automation()" not in source
    assert ".query(" not in source
    assert ".write(" not in source
    assert "CURVE?" not in source
