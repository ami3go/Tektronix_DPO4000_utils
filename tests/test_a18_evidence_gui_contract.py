from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "dpo4000_utils" / "gui_qt" / "composition" / "pages" / "evidence.py"
PAGES_INIT = ROOT / "dpo4000_utils" / "gui_qt" / "composition" / "pages" / "__init__.py"


def test_a18_panel_has_no_raw_instrument_transport() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for forbidden in (".query(", ".write(", "scope.scope", "ResourceManager("):
        assert forbidden not in text
    assert "scope.read_screen_png()" in text
    assert "scope.read_enabled_waveforms(point_count=point_count)" in text
    assert 'retain_session=True' in text


def test_a18_panel_exposes_capture_controls() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for object_name in (
        "A18EvidenceBundlePanel",
        "evidenceScreenCheck",
        "evidenceWaveformCheck",
        "evidencePointsCombo",
        "evidenceSaveButton",
        "evidenceCancelButton",
        "evidenceStatusLabel",
    ):
        assert object_name in text
    for label in ("Full", "1k", "10k", "100k", "1M"):
        assert f'("{label}",' in text


def test_recipe_builder_routes_through_a18_wrapper() -> None:
    text = PAGES_INIT.read_text(encoding="utf-8")
    assert "from .evidence import build_recipe_page" in text
    page = PAGE.read_text(encoding="utf-8")
    assert "class RecipeEvidencePage(RecipePage)" in page
    assert "self.evidence_panel.set_result(result, rule_result)" in page


def test_evidence_work_is_not_done_in_gui_completion_callback() -> None:
    text = PAGE.read_text(encoding="utf-8")
    execute_start = text.index("        def execute(scope: Any) -> EvidenceBundleResult:")
    submit = text.index("        self._run_action(", execute_start)
    body = text[execute_start:submit]
    assert "create_evidence_bundle(" in body
    assert "read_screen_png" in body
    assert "read_enabled_waveforms" in body
