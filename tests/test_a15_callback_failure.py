from __future__ import annotations

from dpo4000_utils.recipe import Recipe, RecipeRunState, RecipeSequencer, RecipeStep


def test_step_callback_failure_marks_recipe_failed_before_io_when_start_callback_fails() -> None:
    class Target:
        def call(self):
            raise AssertionError("should not execute")

    result = RecipeSequencer(Target()).run(
        Recipe("callback", (RecipeStep.call("call"),)),
        on_step_start=lambda _index, _step: (_ for _ in ()).throw(RuntimeError("callback")),
    )
    assert result.state is RecipeRunState.FAILED
    assert result.error == "RuntimeError: callback"
