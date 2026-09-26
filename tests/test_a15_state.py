from __future__ import annotations

from dpo4000_utils.recipe import Recipe, RecipeRunState, RecipeSequencer, RecipeStep


def test_sequencer_starts_idle_and_ends_completed() -> None:
    sequencer = RecipeSequencer(object())
    assert sequencer.state is RecipeRunState.IDLE
    result = sequencer.run(Recipe("noop", (RecipeStep.delay(0),)))
    assert result.state is RecipeRunState.COMPLETED
    assert sequencer.state is RecipeRunState.COMPLETED
