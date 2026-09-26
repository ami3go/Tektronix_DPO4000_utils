from __future__ import annotations

import threading
import time

from dpo4000_utils.recipe import Recipe, RecipeRunState, RecipeSequencer, RecipeStep, RetryPolicy


def test_cancel_interrupts_retry_backoff() -> None:
    entered = threading.Event()

    class Target:
        def fail(self) -> None:
            entered.set()
            raise RuntimeError("expected")

    sequencer = RecipeSequencer(Target(), cancel_poll_s=0.01)
    recipe = Recipe(
        "retry-cancel",
        (
            RecipeStep.call(
                "fail",
                retry=RetryPolicy(attempts=5, delay_s=10.0, backoff=1.0),
            ),
        ),
    )
    holder = {}
    thread = threading.Thread(target=lambda: holder.setdefault("result", sequencer.run(recipe)), daemon=True)
    thread.start()
    assert entered.wait(timeout=1)
    time.sleep(0.02)
    sequencer.cancel()
    thread.join(timeout=1)
    assert not thread.is_alive()
    assert holder["result"].state is RecipeRunState.CANCELLED
