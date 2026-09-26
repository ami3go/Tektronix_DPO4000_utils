from __future__ import annotations

from dataclasses import dataclass

import pytest

from dpo4000_utils.recipe import RecipeResult, RecipeRunState, StepResult
from dpo4000_utils.rules import (
    RuleEngine,
    RuleStatus,
    RuleValidationError,
    recipe_result_values,
    rule_set_from_mapping,
    rule_set_to_mapping,
)


def test_rule_set_mapping_round_trip() -> None:
    document = {
        "version": 1,
        "name": "5 V rail",
        "root": {
            "type": "group",
            "id": "rail",
            "logic": "AND",
            "children": [
                {
                    "type": "compare",
                    "id": "min",
                    "input": "MEAS1",
                    "operator": ">=",
                    "value": 4.95,
                },
                {
                    "type": "compare",
                    "id": "max",
                    "input": "MEAS1",
                    "operator": "<=",
                    "value": 5.05,
                },
            ],
        },
    }
    parsed = rule_set_from_mapping(document)
    assert rule_set_to_mapping(parsed) == document
    assert RuleEngine().evaluate(parsed, {"MEAS1": 5.0}).status is RuleStatus.PASS


def test_unknown_or_future_schema_is_rejected() -> None:
    with pytest.raises(RuleValidationError, match="unsupported rule-set version"):
        rule_set_from_mapping(
            {
                "version": 2,
                "name": "future",
                "root": {
                    "type": "compare",
                    "id": "x",
                    "input": "x",
                    "operator": ">",
                    "value": 0,
                },
            }
        )
    with pytest.raises(RuleValidationError, match="unknown rule-set fields"):
        rule_set_from_mapping(
            {
                "version": 1,
                "name": "bad",
                "root": {
                    "type": "compare",
                    "id": "x",
                    "input": "x",
                    "operator": ">",
                    "value": 0,
                },
                "python": "eval('bad')",
            }
        )
    with pytest.raises(RuleValidationError, match="unknown compare fields"):
        rule_set_from_mapping(
            {
                "version": 1,
                "name": "bad",
                "root": {
                    "type": "compare",
                    "id": "x",
                    "input": "x",
                    "operator": ">",
                    "value": 0,
                    "expression": "__import__('os')",
                },
            }
        )


@dataclass(frozen=True)
class Sample:
    voltage: float
    ripple: float


def test_recipe_result_values_exposes_step_names_indices_and_dataclass_fields() -> None:
    result = RecipeResult(
        "recipe",
        RecipeRunState.COMPLETED,
        1.0,
        2.0,
        (
            StepResult(0, "MEAS1", 1, 1.0, 1.1, 5.0),
            StepResult(1, "rail", 1, 1.1, 1.2, Sample(5.01, 0.02)),
        ),
    )
    values = recipe_result_values(result)
    assert values["MEAS1"] == 5.0
    assert values["step.0"] == 5.0
    assert values["step.MEAS1"] == 5.0
    assert values["rail.voltage"] == 5.01
    assert values["step.1.ripple"] == 0.02


def test_duplicate_step_names_are_not_exposed_as_ambiguous_direct_inputs() -> None:
    result = RecipeResult(
        "recipe",
        RecipeRunState.COMPLETED,
        1.0,
        2.0,
        (
            StepResult(0, "MEAS1", 1, 1.0, 1.1, 4.9),
            StepResult(1, "MEAS1", 1, 1.1, 1.2, 5.1),
        ),
    )
    values = recipe_result_values(result)
    assert "MEAS1" not in values
    assert values["step.0"] == 4.9
    assert values["step.1"] == 5.1


def test_recipe_context_can_drive_compound_pass_fail() -> None:
    result = RecipeResult(
        "recipe",
        RecipeRunState.COMPLETED,
        1.0,
        2.0,
        (StepResult(0, "MEAS1", 1, 1.0, 1.1, 5.0),),
    )
    rules = rule_set_from_mapping(
        {
            "version": 1,
            "name": "rail",
            "root": {
                "type": "group",
                "id": "root",
                "logic": "AND",
                "children": [
                    {"type": "compare", "id": "lo", "input": "MEAS1", "operator": ">=", "value": 4.95},
                    {"type": "compare", "id": "hi", "input": "MEAS1", "operator": "<=", "value": 5.05},
                ],
            },
        }
    )
    assert RuleEngine().evaluate(rules, recipe_result_values(result)).status is RuleStatus.PASS
