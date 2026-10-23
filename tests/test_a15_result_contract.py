from __future__ import annotations

from dpo4000_utils.recipe import Recipe, RecipeRunState, RecipeSequencer, RecipeStep


def test_failed_recipe_records_completed_steps_only_and_error_class() -> None:
    class Target:
        def ok(self):
            return 123

        def fail(self):
            raise ValueError("bad value")

    result = RecipeSequencer(Target()).run(
        Recipe("failure", (RecipeStep.call("ok"), RecipeStep.call("fail")))
    )
    assert result.state is RecipeRunState.FAILED
    assert len(result.steps) == 1
    assert result.steps[0].value == 123
    assert result.error == "ValueError: bad value"
