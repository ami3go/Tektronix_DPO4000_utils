from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
A2_WINDOW = ROOT / "dpo4000_utils" / "gui_qt" / "automation_trigger_window.py"


def test_a2_trigger_window_stays_behind_public_driver_boundary() -> None:
    source = A2_WINDOW.read_text(encoding="utf-8")

    assert "scope.single_acquisition()" in source
    assert "scope.get_acquisition_state()" in source
    assert "scope.get_trigger_state()" in source
    assert "scope.stop_acquisition()" in source
    assert "scope.save_image_path(path)" in source
    assert ".query(" not in source
    assert ".write(" not in source
    assert "ACQUIRE:" not in source
    assert "TRIGGER:" not in source
    assert "HARDCOPY" not in source
