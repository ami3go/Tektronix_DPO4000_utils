from __future__ import annotations

import json
from pathlib import Path

from dpo4000_utils.recipe import RecipeRunState, RecipeSequencer, recipe_from_mapping


def test_minimal_recipe_fixture_loads_and_runs() -> None:
    path = Path(__file__).parent / "data" / "a15_recipe_minimal.json"
    recipe = recipe_from_mapping(json.loads(path.read_text(encoding="utf-8")))
    result = RecipeSequencer(object()).run(recipe)
    assert result.state is RecipeRunState.COMPLETED
