from __future__ import annotations

from pathlib import Path

import pytest

from dpo4000_utils.automation.profiles import AutomationProfile, AutomationProfileError, load_automation_profile


def test_a10_rejects_non_finite_numbers() -> None:
    with pytest.raises(AutomationProfileError, match="Non-finite"):
        AutomationProfile(name="bad", config={"mode": "Periodic Image", "widgets": {"x": float("nan")}})


def test_a10_loader_rejects_json_nan(tmp_path: Path) -> None:
    path = tmp_path / "nan.json"
    path.write_text(
        '{"schema_version": 1, "name": "bad", "config": {"mode": "Periodic Image", "x": NaN}}',
        encoding="utf-8",
    )
    with pytest.raises(AutomationProfileError):
        load_automation_profile(path)


def test_a10_review_preflights_before_super_apply() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "dpo4000_utils" / "gui_qt" / "automation_profiles_review_window.py"
    ).read_text(encoding="utf-8")
    method = source.split("def _apply_automation_profile_config", 1)[1]
    assert method.index("self._preflight_automation_profile_config(config)") < method.index(
        "super()._apply_automation_profile_config(config)"
    )
    assert "FILE_PAGE_INDEX" in source
    assert ".query(" not in source
    assert ".write(" not in source
