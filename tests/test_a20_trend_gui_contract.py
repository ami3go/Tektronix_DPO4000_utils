from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "dpo4000_utils" / "gui_qt" / "composition" / "pages" / "trend.py"
LEGACY = ROOT / "dpo4000_utils" / "gui_qt" / "composition" / "legacy_surface.py"


def test_trend_panel_uses_public_driver_boundary_only() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for forbidden in (".query(", ".write(", "scope.scope", "ResourceManager("):
        assert forbidden not in text
    assert "scope.read_measurement_value(slot)" in text
    assert "retain_session=True" in text


def test_trend_poll_has_explicit_backpressure() -> None:
    text = PAGE.read_text(encoding="utf-8")
    assert "self._poll_in_flight" in text
    assert "self._skipped_ticks += 1" in text
    assert "QTimer" in text
    assert "on_success=success" in text
    assert "on_error=failure" in text


def test_trend_controls_and_scaling_choices_are_present() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for object_name in (
        "measurementTrendPanel",
        "measurementTrendPlot",
        "measurementTrendInterval",
        "measurementTrendCapacity",
        "measurementTrendRenderPoints",
        "measurementTrendStart",
        "measurementTrendStop",
        "measurementTrendClear",
        "measurementTrendStatus",
    ):
        assert object_name in text
    assert "100_000" in text
    assert "5_000" in text


def test_composition_attaches_a20_to_measurement_page() -> None:
    text = LEGACY.read_text(encoding="utf-8")
    assert "attach_measurement_trend_panel" in text
    assert "def _build_measurement_tab" in text
