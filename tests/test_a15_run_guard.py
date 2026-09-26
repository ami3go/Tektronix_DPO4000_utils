from __future__ import annotations

import threading

import pytest

from dpo4000_utils.recipe import Recipe, RecipeSequencer, RecipeStep


class Target:
    def blocked(self) -> None:
        return None


def test_second_run_is_rejected_while_running() -> None:
    entered = threading.Event()
    release = threading.Event()

    class BlockingTarget:
        def blocked(self) -> None:
            entered.set()
            release.wait(timeout=2)

    sequencer = RecipeSequencer(BlockingTarget())
    recipe = Recipe("blocking", (RecipeStep.call("blocked"),))
    thread = threading.Thread(target=sequencer.run, args=(recipe,), daemon=True)
    thread.start()
    assert entered.wait(timeout=1)
    with pytest.raises(RuntimeError, match="already running"):
        sequencer.run(recipe)
    release.set()
    thread.join(timeout=2)
    assert not thread.is_alive()
