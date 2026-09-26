from __future__ import annotations

from dpo4000_utils.recipe import RecipeRunState, RecipeSequencer


def test_pause_and_resume_are_noops_while_idle() -> None:
    sequencer = RecipeSequencer(object())
    sequencer.pause()
    assert sequencer.state is RecipeRunState.IDLE
    sequencer.resume()
    assert sequencer.state is RecipeRunState.IDLE
