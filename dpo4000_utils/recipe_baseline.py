"""A15 recipe/sequencer timing capture for the controlled R0-T baseline."""

from __future__ import annotations

import time
from typing import Any

from .baseline_capture import distribution
from .recipe import Recipe, RecipeRunState, RecipeSequencer, RecipeStep


def _require_positive_int(value: int, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be an integer >= 1")
    return value


def capture_recipe_timing(
    scope: Any,
    *,
    reps: int = 20,
    dispatch_steps: int = 1_000,
) -> dict[str, Any]:
    """Measure A15 completion latency and local per-step dispatch overhead.

    ``recipe_completion`` uses a read-only hardware recipe so it is safe for normal
    qualification. ``step_dispatch_overhead`` uses a local no-op target to isolate
    sequencer/preflight cost from VISA latency.
    """
    reps = _require_positive_int(reps, field="reps")
    dispatch_steps = _require_positive_int(
        dispatch_steps,
        field="dispatch_steps",
    )

    read_only = Recipe(
        "A15 R0-T read-only",
        (
            RecipeStep.call("get_trigger_holdoff"),
            RecipeStep.call("get_trigger_configuration"),
        ),
    )
    completion_samples: list[float] = []
    for _ in range(reps):
        started = time.perf_counter()
        result = RecipeSequencer(scope).run(read_only)
        completion_samples.append(time.perf_counter() - started)
        if result.state is not RecipeRunState.COMPLETED:
            raise RuntimeError(
                f"A15 timing recipe failed: {result.error or result.state.value}"
            )

    class NoopTarget:
        def ping(self, value: int) -> int:
            return value

    dispatch_recipe = Recipe(
        "A15 dispatch baseline",
        tuple(RecipeStep.call("ping", index) for index in range(dispatch_steps)),
    )
    dispatch_samples: list[float] = []
    target = NoopTarget()
    for _ in range(reps):
        started = time.perf_counter()
        result = RecipeSequencer(target).run(dispatch_recipe)
        elapsed = time.perf_counter() - started
        if result.state is not RecipeRunState.COMPLETED:
            raise RuntimeError(
                f"A15 dispatch baseline failed: {result.error or result.state.value}"
            )
        dispatch_samples.append(elapsed / dispatch_steps)

    return {
        "recipe_completion": distribution(completion_samples),
        "step_dispatch_overhead": distribution(dispatch_samples),
        "dispatch_steps_per_sample": dispatch_steps,
    }


__all__ = ["capture_recipe_timing"]
