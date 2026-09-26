from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PAGE = REPO_ROOT / "dpo4000_utils" / "gui_qt" / "composition" / "pages" / "recipe.py"


def test_recipe_page_has_no_raw_scope_transport_access() -> None:
    text = PAGE.read_text(encoding="utf-8")
    assert ".query(" not in text
    assert ".write(" not in text
    assert "visa" not in text.lower()
    assert "SCPI" in text


def test_recipe_page_exposes_expected_controls() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for object_name in (
        "recipeLoadButton",
        "recipeValidateButton",
        "recipeRunButton",
        "recipePauseButton",
        "recipeResumeButton",
        "recipeCancelButton",
        "recipeJsonEditor",
        "recipeResultsTable",
    ):
        assert object_name in text


def test_recipe_page_uses_worker_action_boundary() -> None:
    text = PAGE.read_text(encoding="utf-8")
    assert "self._run_action(" in text
    assert "on_success=self._run_finished" in text
    assert "on_error=self._run_error" in text
