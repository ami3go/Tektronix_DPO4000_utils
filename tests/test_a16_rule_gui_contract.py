from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "dpo4000_utils" / "gui_qt" / "composition" / "pages" / "recipe.py"


def test_rule_ui_has_no_raw_instrument_transport() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for forbidden in (".query(", ".write(", "scope.scope", "ResourceManager("):
        assert forbidden not in text
    assert "RuleEngine().evaluate" in text
    assert "recipe_result_values" in text


def test_rule_ui_exposes_rule_editor_and_results() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for object_name in (
        "ruleSetLoadButton",
        "ruleSetSaveButton",
        "ruleSetValidateButton",
        "ruleSetJsonEditor",
        "ruleSetResultsTable",
    ):
        assert object_name in text


def test_a16_rule_evaluation_happens_after_completed_recipe() -> None:
    text = PAGE.read_text(encoding="utf-8")
    assert "result.state is RecipeRunState.FAILED" in text
    assert "result.state is RecipeRunState.CANCELLED" in text
    assert "RuleEngine().evaluate(rules, recipe_result_values(result))" in text
    assert 'f"{result.duration_s:.3f}s — {rule_result.status.value}"' in text
