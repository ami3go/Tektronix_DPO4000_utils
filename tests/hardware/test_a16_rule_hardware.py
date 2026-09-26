"""Read-only A16 integration qualification against a real DPO4000 scope."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from dpo4000_utils import DPO4054
from dpo4000_utils.connection import visaResourceAddr
from dpo4000_utils.recipe import Recipe, RecipeRunState, RecipeSequencer, RecipeStep
from dpo4000_utils.rules import (
    CompareOperator,
    RuleEngine,
    RuleSet,
    RuleStatus,
    ScalarRule,
    recipe_result_values,
)

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


@pytest.fixture(scope="module")
def a16_scope() -> Iterator[DPO4054]:
    if not _env_enabled("DPO4000_HARDWARE"):
        pytest.skip("Set DPO4000_HARDWARE=1 to run A16 hardware qualification.")
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
        identity = scope.query_identity()
        expected = os.getenv("DPO4000_EXPECT_IDN", "TEKTRONIX,DPO4054").strip()
        assert expected.upper() in identity.upper()
        yield scope
    finally:
        scope.disconnect()


@pytest.mark.hardware
def test_a16_recipe_value_drives_read_only_pass_fail(a16_scope: DPO4054) -> None:
    recipe = Recipe(
        "A16 holdoff read",
        (RecipeStep.call("get_trigger_holdoff", name="HOLDOFF"),),
    )
    recipe_result = RecipeSequencer(a16_scope).run(recipe)
    assert recipe_result.state is RecipeRunState.COMPLETED

    rule_set = RuleSet(
        "Holdoff sanity",
        ScalarRule(
            "holdoff_non_negative",
            "HOLDOFF",
            CompareOperator.GTE,
            value=0.0,
        ),
    )
    result = RuleEngine().evaluate(rule_set, recipe_result_values(recipe_result))
    assert result.status is RuleStatus.PASS
    assert result.root.actual is not None
    assert result.root.actual >= 0.0
