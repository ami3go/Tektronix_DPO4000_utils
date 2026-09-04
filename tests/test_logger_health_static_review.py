from __future__ import annotations

from pathlib import Path


def test_l13_gui_avoids_ruff_e731_assigned_lambda() -> None:
    source = (
        Path(__file__).parents[1]
        / "dpo4000_utils"
        / "gui_qt"
        / "logger_health_window.py"
    ).read_text(encoding="utf-8")
    assert "= lambda" not in source
