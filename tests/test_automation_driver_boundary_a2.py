from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
A2_WINDOW = ROOT / "dpo4000_utils" / "gui_qt" / "automation_trigger_window.py"
A2_REVIEW_WINDOW = ROOT / "dpo4000_utils" / "gui_qt" / "automation_trigger_review_window.py"


def test_a2_trigger_window_stays_behind_public_driver_boundary() -> None:
    source = A2_WINDOW.read_text(encoding="utf-8")

    assert "scope.single_acquisition()" in source
    assert "scope.get_acquisition_state()" in source
    assert "scope.get_trigger_state()" in source
    assert "scope.stop_acquisition()" in source
    assert "scope.save_image_path(path)" in source
    assert ".query(" not in source
    assert ".write(" not in source
    assert "HARDCOPY" not in source


def test_reviewed_a2_recipe_does_not_depend_on_scpi_command_spelling() -> None:
    source = A2_REVIEW_WINDOW.read_text(encoding="utf-8")

    assert "ACQUIRE:" not in source
    assert "TRIGGER:" not in source
    assert ".query(" not in source
    assert ".write(" not in source
