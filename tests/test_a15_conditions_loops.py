from __future__ import annotations

import json

import pytest

from dpo4000_utils.recipe import (
    MAX_RECIPE_STEPS,
    ConditionInvalidPolicy,
    Recipe,
    RecipeRunState,
    RecipeSequencer,
    RecipeStep,
    RecipeValidationError,
    RepeatBlock,
    recipe_from_mapping,
    recipe_to_mapping,
)
from dpo4000_utils.rules import CompareOperator, ScalarRule, recipe_result_values


class _Target:
    """Fake driver: each read returns the next value from a script."""

    def __init__(self, readings=()) -> None:
        self.readings = list(readings)
        self.calls: list[str] = []

    def read(self) -> float:
        self.calls.append("read")
        return self.readings.pop(0)

    def act(self) -> str:
        self.calls.append("act")
        return "ok"


def _sequencer(target: _Target) -> RecipeSequencer:
    return RecipeSequencer(target, sleep=lambda _s: None)


def _when(input_name: str, operator: str, value: float) -> ScalarRule:
    return ScalarRule("when", input_name, CompareOperator(operator), value=value)


def test_if_else_branches_on_a_previous_value() -> None:
    recipe = Recipe(
        "branch",
        (
            RecipeStep.call("read", name="v"),
            RecipeStep.call("act", name="high", when=_when("v", ">=", 5.0)),
            RecipeStep.call("act", name="low", when=_when("v", "<", 5.0)),
        ),
    )
    target = _Target([7.0])
    result = _sequencer(target).run(recipe)
    assert result.state is RecipeRunState.COMPLETED
    assert [(step.name, step.skipped, step.attempts) for step in result.steps] == [
        ("v", False, 1),
        ("high", False, 1),
        ("low", True, 0),
    ]
    assert target.calls == ["read", "act"]


def test_invalid_condition_fails_by_default_before_any_io_for_that_step() -> None:
    recipe = Recipe(
        "invalid",
        (RecipeStep.call("act", name="guarded", when=_when("missing", ">", 0.0)),),
    )
    target = _Target()
    result = _sequencer(target).run(recipe)
    assert result.state is RecipeRunState.FAILED
    assert "condition for step 'guarded' is invalid" in (result.error or "")
    assert target.calls == []


def test_invalid_condition_can_skip() -> None:
    recipe = Recipe(
        "invalid-skip",
        (
            RecipeStep.call(
                "act",
                name="guarded",
                when=_when("missing", ">", 0.0),
                when_invalid=ConditionInvalidPolicy.SKIP,
            ),
            RecipeStep.call("act", name="after"),
        ),
    )
    target = _Target()
    result = _sequencer(target).run(recipe)
    assert result.state is RecipeRunState.COMPLETED
    assert [step.skipped for step in result.steps] == [True, False]
    assert target.calls == ["act"]


@pytest.mark.parametrize(
    ("reply", "expected_high"),
    [
        ("999.8784E+0", True),  # real DPO4054 MEAS1=FREQUENCY reply
        ("2.6258", True),
        ("  1.0001E+3\n", True),
        ("-4.5E-1", False),
        (".5", False),
        ("7.", True),
    ],
)
def test_measurement_text_is_compared_as_a_number(reply: str, expected_high: bool) -> None:
    """read_measurement_value() returns instrument text; branching on it must work."""
    recipe = Recipe(
        "text",
        (
            RecipeStep.call("read", name="v"),
            RecipeStep.call("act", name="high", when=_when("v", ">=", 1.0)),
            RecipeStep.call("act", name="low", when=_when("v", "<", 1.0)),
        ),
    )
    result = _sequencer(_Target([reply])).run(recipe)
    assert result.state is RecipeRunState.COMPLETED
    assert [step.skipped for step in result.steps[1:]] == [not expected_high, expected_high]


@pytest.mark.parametrize(
    "reply",
    ["9.91E+37", "9.91E37", "-9.91E+37", "nan", "inf", "-inf", "1_000", "0x10", "1e", "12 V", "", "abc"],
)
def test_non_measurement_text_stays_invalid(reply: str) -> None:
    """The no-measurement sentinel and malformed text must never compare as numbers."""
    recipe = Recipe(
        "sentinel",
        (
            RecipeStep.call("read", name="v"),
            RecipeStep.call("act", name="guarded", when=_when("v", ">=", 0.0)),
        ),
    )
    target = _Target([reply])
    result = _sequencer(target).run(recipe)
    assert result.state is RecipeRunState.FAILED
    assert "is not numeric" in (result.error or "")
    assert target.calls == ["read"]


def test_sentinel_can_be_skipped_with_on_invalid_skip() -> None:
    recipe = Recipe(
        "sentinel-skip",
        (
            RecipeStep.call("read", name="v"),
            RecipeStep.call(
                "act", name="guarded", when=_when("v", ">=", 0.0),
                when_invalid=ConditionInvalidPolicy.SKIP,
            ),
        ),
    )
    target = _Target(["9.91E+37"])
    result = _sequencer(target).run(recipe)
    assert result.state is RecipeRunState.COMPLETED
    assert [step.skipped for step in result.steps] == [False, True]
    assert target.calls == ["read"]


def test_repeat_is_expanded_and_preserved_in_definition() -> None:
    recipe = Recipe(
        "loop",
        (
            RecipeStep.call("act", name="setup"),
            RepeatBlock(3, (RecipeStep.call("read", name="v"), RecipeStep.delay(0.0))),
        ),
    )
    assert recipe.version == 2
    assert len(recipe.definition) == 2
    assert [step.name for step in recipe.steps] == ["setup"] + ["v", "Delay 0s"] * 3
    result = _sequencer(_Target([1.0, 2.0, 3.0])).run(recipe)
    assert result.state is RecipeRunState.COMPLETED
    assert [step.index for step in result.steps] == list(range(7))


def test_repeat_until_skips_remaining_iterations_without_io() -> None:
    # Read once, then keep re-reading while the latest value is below 5.
    recipe = Recipe(
        "until",
        (
            RecipeStep.call("read", name="v"),
            RepeatBlock(10, (RecipeStep.call("read", name="v", when=_when("v", "<", 5.0)),)),
        ),
    )
    target = _Target([1.0, 3.0, 6.0])
    result = _sequencer(target).run(recipe)
    assert result.state is RecipeRunState.COMPLETED
    assert target.calls == ["read", "read", "read"]
    assert [step.skipped for step in result.steps] == [False, False, False] + [True] * 8
    # Skipped steps carry no value; rules see the skip as a missing input.
    assert recipe_result_values(result)["step.0"] == 1.0


def test_condition_sees_latest_value_for_repeated_names() -> None:
    recipe = Recipe(
        "latest",
        (
            RepeatBlock(2, (RecipeStep.call("read", name="v"),)),
            RecipeStep.call("act", name="only-if-last-high", when=_when("v", ">", 5.0)),
        ),
    )
    target = _Target([1.0, 9.0])
    result = _sequencer(target).run(recipe)
    assert result.steps[-1].skipped is False
    target = _Target([9.0, 1.0])
    result = _sequencer(target).run(recipe)
    assert result.steps[-1].skipped is True


def test_nested_calls_are_visible_in_flat_steps_for_safety_checks() -> None:
    recipe = Recipe("nested", (RepeatBlock(2, (RepeatBlock(2, (RecipeStep.call("act"),)),)),))
    assert [step.method for step in recipe.steps] == ["act"] * 4


def test_denied_method_inside_repeat_is_rejected() -> None:
    with pytest.raises(RecipeValidationError):
        Recipe("deny", (RepeatBlock(2, (RecipeStep.call("disconnect"),)),))


@pytest.mark.parametrize("count", [0, -1, True, 1.5, 10_001])
def test_repeat_count_is_bounded(count) -> None:
    with pytest.raises(RecipeValidationError):
        RepeatBlock(count, (RecipeStep.call("act"),))


def test_expansion_is_bounded_by_max_recipe_steps() -> None:
    inner = RepeatBlock(100, (RecipeStep.call("act"),))
    with pytest.raises(RecipeValidationError, match="expand"):
        Recipe("big", (RepeatBlock(MAX_RECIPE_STEPS // 100 + 1, (inner,)),))


def test_nesting_depth_is_bounded() -> None:
    item = RecipeStep.call("act")
    for _ in range(5):
        item = RepeatBlock(1, (item,))
    with pytest.raises(RecipeValidationError, match="nested"):
        Recipe("deep", (item,))


def test_mapping_round_trip_preserves_structure_and_conditions() -> None:
    document = {
        "version": 2,
        "name": "doc",
        "steps": [
            {"kind": "call", "name": "v", "method": "read"},
            {
                "kind": "repeat",
                "name": "Retry until high",
                "count": 3,
                "steps": [
                    {
                        "kind": "call",
                        "name": "v",
                        "method": "read",
                        "when": {"input": "v", "operator": "<", "value": 5.0, "on_invalid": "skip"},
                    },
                    {"kind": "delay", "name": "wait", "seconds": 0.0, "when": {"input": "v", "operator": "<", "value": 5.0}},
                ],
            },
        ],
    }
    recipe = recipe_from_mapping(document)
    assert len(recipe.steps) == 7
    mapping = recipe_to_mapping(recipe)
    assert mapping["version"] == 2
    assert mapping["steps"][1]["kind"] == "repeat"
    assert mapping["steps"][1]["steps"][0]["when"] == {
        "input": "v",
        "operator": "<",
        "value": 5.0,
        "on_invalid": "skip",
    }
    assert recipe_from_mapping(json.loads(json.dumps(mapping))) == recipe


def test_v1_documents_are_unchanged() -> None:
    document = {"version": 1, "name": "v1", "steps": [{"kind": "delay", "name": "d", "seconds": 0.5}]}
    recipe = recipe_from_mapping(document)
    assert recipe.version == 1
    assert recipe_to_mapping(recipe)["version"] == 1
    assert "when" not in recipe_to_mapping(recipe)["steps"][0]


@pytest.mark.parametrize(
    "step",
    [
        {"kind": "repeat", "count": 2, "steps": [{"kind": "delay", "seconds": 0}]},
        {"kind": "delay", "seconds": 0, "when": {"input": "v", "operator": ">", "value": 1}},
    ],
)
def test_v2_features_require_version_2(step) -> None:
    with pytest.raises(RecipeValidationError, match="version 2"):
        recipe_from_mapping({"version": 1, "name": "x", "steps": [step]})


@pytest.mark.parametrize(
    "when",
    [
        {"input": "v", "operator": ">"},
        {"input": "v", "operator": "~", "value": 1},
        {"input": "v", "operator": ">", "value": 1, "expr": "__import__('os')"},
        {"input": "v", "operator": ">", "value": 1, "on_invalid": "ignore"},
        "v > 1",
    ],
)
def test_malformed_conditions_rejected(when) -> None:
    with pytest.raises(RecipeValidationError):
        recipe_from_mapping(
            {"version": 2, "name": "x", "steps": [{"kind": "call", "method": "act", "when": when}]}
        )


def test_repeat_rejects_unknown_fields_and_empty_body() -> None:
    with pytest.raises(RecipeValidationError):
        recipe_from_mapping(
            {"version": 2, "name": "x", "steps": [{"kind": "repeat", "count": 2, "steps": [], "until": 1}]}
        )
    with pytest.raises(RecipeValidationError):
        recipe_from_mapping({"version": 2, "name": "x", "steps": [{"kind": "repeat", "count": 2, "steps": []}]})


def test_cancel_during_loop_stops_promptly() -> None:
    recipe = Recipe("cancel", (RepeatBlock(1000, (RecipeStep.call("act"),)),))
    target = _Target()
    sequencer = _sequencer(target)

    def stop_after_three(result) -> None:
        if result.index == 2:
            sequencer.cancel()

    result = sequencer.run(recipe, on_step_finish=stop_after_three)
    assert result.state is RecipeRunState.CANCELLED
    assert len(target.calls) == 3
