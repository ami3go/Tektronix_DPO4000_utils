from __future__ import annotations

from dpo4000_utils.recipe import Recipe, RecipeRunState, RecipeSequencer, RecipeStep, RetryPolicy


def test_retry_exhaustion_reports_final_error() -> None:
    class Target:
        def fail(self):
            raise OSError("down")

    result = RecipeSequencer(Target()).run(
        Recipe(
            "exhaust",
            (RecipeStep.call("fail", retry=RetryPolicy(attempts=2)),),
        )
    )
    assert result.state is RecipeRunState.FAILED
    assert result.error == "OSError: down"
