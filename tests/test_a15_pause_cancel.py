from __future__ import annotations

import threading
import time

from dpo4000_utils.recipe import Recipe, RecipeRunState, RecipeSequencer, RecipeStep


def test_cancel_interrupts_long_delay() -> None:
    sequencer = RecipeSequencer(object(), cancel_poll_s=0.01)
    recipe = Recipe("cancel-delay", (RecipeStep.delay(10.0),))
    holder = {}

    thread = threading.Thread(target=lambda: holder.setdefault("result", sequencer.run(recipe)), daemon=True)
    thread.start()
    time.sleep(0.02)
    sequencer.cancel()
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert holder["result"].state is RecipeRunState.CANCELLED


def test_pause_then_resume_stops_progress_between_checkpoints() -> None:
    entered = threading.Event()
    release = threading.Event()

    class Target:
        def first(self) -> None:
            entered.set()
            release.wait(timeout=2)

        def second(self) -> None:
            pass

    target = Target()
    sequencer = RecipeSequencer(target, cancel_poll_s=0.01)
    recipe = Recipe("pause", (RecipeStep.call("first"), RecipeStep.call("second")))
    holder = {}
    thread = threading.Thread(target=lambda: holder.setdefault("result", sequencer.run(recipe)), daemon=True)
    thread.start()
    assert entered.wait(timeout=1)
    sequencer.pause()
    release.set()
    time.sleep(0.03)
    assert thread.is_alive()
    sequencer.resume()
    thread.join(timeout=1)
    assert holder["result"].state is RecipeRunState.COMPLETED
