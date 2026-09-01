from __future__ import annotations

from pathlib import Path


def test_l2_exposes_math_without_raw_scope_io() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "dpo4000_utils" / "gui_qt" / "logger_math_window.py").read_text(encoding="utf-8")
    assert 'QCheckBox("MATH")' in source
    assert 'sources.append("MATH")' in source
    assert ".query(" not in source
    assert ".write(" not in source
