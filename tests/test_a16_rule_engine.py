from __future__ import annotations

from datetime import datetime, timezone
import math

import pytest

from dpo4000_utils.rules import (
    CompareOperator,
    LogicOperator,
    RuleEngine,
    RuleGroup,
    RuleSet,
    RuleStatus,
    RuleValidationError,
    ScalarRule,
)


@pytest.mark.parametrize(
    ("operator", "actual", "expected", "status"),
    [
        (CompareOperator.GT, 2.0, 1.0, RuleStatus.PASS),
        (CompareOperator.GT, 1.0, 1.0, RuleStatus.FAIL),
        (CompareOperator.GTE, 1.0, 1.0, RuleStatus.PASS),
        (CompareOperator.LT, 0.9, 1.0, RuleStatus.PASS),
        (CompareOperator.LT, 1.0, 1.0, RuleStatus.FAIL),
        (CompareOperator.LTE, 1.0, 1.0, RuleStatus.PASS),
        (CompareOperator.EQ, 1.0, 1.0, RuleStatus.PASS),
        (CompareOperator.NE, 1.000001, 1.0, RuleStatus.PASS),
    ],
)
def test_simple_numeric_operators(operator, actual, expected, status) -> None:
    rule = ScalarRule("r", "x", operator, value=expected)
    result = RuleEngine().evaluate(RuleSet("rules", rule), {"x": actual})
    assert result.status is status
    assert result.root.actual == actual


def test_inside_and_outside_are_inclusive_complements_at_boundaries() -> None:
    inside = ScalarRule("inside", "x", CompareOperator.INSIDE, low=1.0, high=2.0)
    outside = ScalarRule("outside", "x", CompareOperator.OUTSIDE, low=1.0, high=2.0)
    engine = RuleEngine()
    for value in (1.0, 2.0):
        assert engine.evaluate(RuleSet("i", inside), {"x": value}).status is RuleStatus.PASS
        assert engine.evaluate(RuleSet("o", outside), {"x": value}).status is RuleStatus.FAIL
    assert engine.evaluate(RuleSet("o", outside), {"x": 0.999999}).status is RuleStatus.PASS
    assert engine.evaluate(RuleSet("o", outside), {"x": 2.000001}).status is RuleStatus.PASS


def test_absolute_and_relative_delta() -> None:
    absolute = ScalarRule(
        "abs",
        "x",
        CompareOperator.ABS_DELTA_LTE,
        reference=10.0,
        tolerance=0.5,
    )
    relative = ScalarRule(
        "rel",
        "x",
        CompareOperator.REL_DELTA_LTE,
        reference=100.0,
        tolerance=0.01,
    )
    engine = RuleEngine()
    assert engine.evaluate(RuleSet("a", absolute), {"x": 10.5}).status is RuleStatus.PASS
    assert engine.evaluate(RuleSet("a", absolute), {"x": 10.500001}).status is RuleStatus.FAIL
    assert engine.evaluate(RuleSet("r", relative), {"x": 101.0}).status is RuleStatus.PASS
    assert engine.evaluate(RuleSet("r", relative), {"x": 101.0001}).status is RuleStatus.FAIL


def test_relative_delta_zero_reference_is_invalid_never_pass() -> None:
    rule = ScalarRule(
        "rel",
        "x",
        CompareOperator.REL_DELTA_LTE,
        reference=0.0,
        tolerance=0.1,
    )
    result = RuleEngine().evaluate(RuleSet("rules", rule), {"x": 0.0})
    assert result.status is RuleStatus.INVALID
    assert "zero" in result.root.reason


@pytest.mark.parametrize("actual", [None, True, "1", math.nan, math.inf, -math.inf])
def test_invalid_values_never_pass(actual) -> None:
    rule = ScalarRule("r", "x", CompareOperator.GTE, value=0.0)
    result = RuleEngine().evaluate(RuleSet("rules", rule), {"x": actual})
    assert result.status is RuleStatus.INVALID


def test_missing_value_is_invalid() -> None:
    rule = ScalarRule("r", "missing", CompareOperator.GTE, value=0.0)
    result = RuleEngine().evaluate(RuleSet("rules", rule), {})
    assert result.status is RuleStatus.INVALID
    assert "missing" in result.root.reason


def test_and_or_not_have_deterministic_invalid_semantics() -> None:
    passed = ScalarRule("pass", "p", CompareOperator.GTE, value=1.0)
    failed = ScalarRule("fail", "f", CompareOperator.GTE, value=1.0)
    invalid = ScalarRule("invalid", "missing", CompareOperator.GTE, value=1.0)
    engine = RuleEngine()

    and_fail = RuleGroup("and-fail", LogicOperator.AND, (failed, invalid))
    assert engine.evaluate(RuleSet("x", and_fail), {"f": 0.0}).status is RuleStatus.FAIL

    and_invalid = RuleGroup("and-invalid", LogicOperator.AND, (passed, invalid))
    assert engine.evaluate(RuleSet("x", and_invalid), {"p": 1.0}).status is RuleStatus.INVALID

    or_pass = RuleGroup("or-pass", LogicOperator.OR, (passed, invalid))
    assert engine.evaluate(RuleSet("x", or_pass), {"p": 1.0}).status is RuleStatus.PASS

    or_invalid = RuleGroup("or-invalid", LogicOperator.OR, (failed, invalid))
    assert engine.evaluate(RuleSet("x", or_invalid), {"f": 0.0}).status is RuleStatus.INVALID

    not_pass = RuleGroup("not", LogicOperator.NOT, (failed,))
    assert engine.evaluate(RuleSet("x", not_pass), {"f": 0.0}).status is RuleStatus.PASS


def test_timestamp_is_stable_across_entire_rule_tree() -> None:
    stamp = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    root = RuleGroup(
        "root",
        LogicOperator.AND,
        (
            ScalarRule("a", "a", CompareOperator.GTE, value=0.0),
            ScalarRule("b", "b", CompareOperator.LTE, value=1.0),
        ),
    )
    result = RuleEngine().evaluate(RuleSet("rules", root), {"a": 1, "b": 1}, timestamp=stamp)
    assert {item.timestamp for item in result.evaluations} == {stamp.isoformat()}


def test_duplicate_ids_and_invalid_rule_configuration_are_rejected() -> None:
    a = ScalarRule("dup", "a", CompareOperator.GTE, value=0.0)
    b = ScalarRule("dup", "b", CompareOperator.LTE, value=1.0)
    with pytest.raises(RuleValidationError, match="duplicate"):
        RuleSet("rules", RuleGroup("root", LogicOperator.AND, (a, b)))
    with pytest.raises(RuleValidationError, match="low must"):
        ScalarRule("range", "x", CompareOperator.INSIDE, low=2.0, high=1.0)
    with pytest.raises(RuleValidationError, match="tolerance"):
        ScalarRule("delta", "x", CompareOperator.ABS_DELTA_LTE, reference=1.0, tolerance=-1.0)
