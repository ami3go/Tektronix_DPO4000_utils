from __future__ import annotations

from pathlib import Path


def test_a9_review_binds_preview_to_resolved_root_and_runs_startup_cleanup() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "dpo4000_utils" / "gui_qt" / "automation_retention_review_window.py"
    ).read_text(encoding="utf-8")
    assert "_retention_preview_root" in source
    assert "_automatic_retention_authorized_for_current_root" in source
    assert "Output folder changed after the retention preview" in source
    assert "self._apply_retention_after_event()" in source
    assert ".query(" not in source
    assert ".write(" not in source
