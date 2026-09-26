"""Opt-in A15 recipe/sequencer qualification against a real DPO4000 scope."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from dpo4000_utils import DPO4054
from dpo4000_utils.connection import visaResourceAddr
from dpo4000_utils.recipe import (
    Recipe,
    RecipeRunState,
    RecipeSequencer,
    RecipeStep,
)
from dpo4000_utils.recipe_baseline import capture_recipe_timing

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


@pytest.fixture(scope="module")
def a15_scope() -> Iterator[DPO4054]:
    if not _env_enabled("DPO4000_HARDWARE"):
        pytest.skip("Set DPO4000_HARDWARE=1 to run A15 hardware qualification.")
    resource = os.getenv("DPO4000_RESOURCE", visaResourceAddr).strip()
    if not resource:
        pytest.skip("Set DPO4000_RESOURCE to the oscilloscope VISA resource.")
    scope = DPO4054(
        resource,
        auto_connect=False,
        timeout_ms=int(os.getenv("DPO4000_TIMEOUT_MS", "20000")),
    )
    scope.connect()
    try:
        yield scope
    finally:
        scope.disconnect()


@pytest.mark.hardware
def test_a15_read_only_recipe_executes_on_dpo4054(a15_scope: DPO4054) -> None:
    recipe = Recipe(
        "A15 DPO4054 read-only",
        (
            RecipeStep.call("query_identity"),
            RecipeStep.call("get_trigger_holdoff"),
            RecipeStep.call("get_trigger_configuration"),
        ),
    )
    result = RecipeSequencer(a15_scope).run(recipe)
    assert result.state is RecipeRunState.COMPLETED
    assert len(result.steps) == 3
    assert "DPO" in str(result.steps[0].value).upper()
    assert float(result.steps[1].value) >= 0


@pytest.mark.hardware
def test_a15_reversible_recipe_restores_holdoff(a15_scope: DPO4054) -> None:
    if not _env_enabled("DPO4000_ENABLE_WRITE_TESTS"):
        pytest.skip("Set DPO4000_ENABLE_WRITE_TESTS=1 for reversible A15 qualification.")

    original = a15_scope.get_trigger_holdoff()
    recipe = Recipe(
        "A15 reversible holdoff",
        (
            RecipeStep.call(
                "set_trigger_holdoff",
                original,
                name="Write existing holdoff",
            ),
            RecipeStep.delay(0.05, name="Settle"),
            RecipeStep.call(
                "get_trigger_holdoff",
                name="Verify holdoff",
            ),
        ),
    )
    try:
        result = RecipeSequencer(a15_scope).run(recipe)
        assert result.state is RecipeRunState.COMPLETED
        assert float(result.steps[-1].value) == pytest.approx(original)
    finally:
        a15_scope.set_trigger_holdoff(original, verify=False)
    assert a15_scope.get_trigger_holdoff() == pytest.approx(original)


@pytest.mark.hardware
def test_a15_r0_t_candidate_capture(a15_scope: DPO4054) -> None:
    timing = capture_recipe_timing(a15_scope, reps=3, dispatch_steps=250)
    assert timing["recipe_completion"]["sample_count"] == 3
    assert timing["step_dispatch_overhead"]["sample_count"] == 3
    assert timing["recipe_completion"]["p95"] >= 0
    assert timing["step_dispatch_overhead"]["p95"] >= 0
