from __future__ import annotations

from dpo4000_utils.recipe import Recipe, RecipeSequencer, RecipeStep, RetryPolicy


def test_step_start_callback_runs_once_for_retries() -> None:
    calls = []
    starts = []

    class Target:
        def flaky(self):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("retry")
            return "ok"

    result = RecipeSequencer(Target()).run(
        Recipe("retry", (RecipeStep.call("flaky", retry=RetryPolicy(attempts=2)),)),
        on_step_start=lambda index, _step: starts.append(index),
    )
    assert starts == [0]
    assert result.steps[0].attempts == 2
