from __future__ import annotations

import pytest

from dpo4000_utils.rules import (
    CompareOperator,
    LogicOperator,
    MAX_RULE_DEPTH,
    MAX_RULE_NODES,
    RuleEngine,
    RuleGroup,
    RuleSet,
    RuleStatus,
    RuleValidationError,
    ScalarRule,
)


def test_rule_tree_at_node_limit_evaluates_deterministically() -> None:
    # The root counts as one node, leaving MAX_RULE_NODES - 1 scalar children.
    children = tuple(
        ScalarRule(f"r{i}", "x", CompareOperator.GTE, value=0.0)
        for i in range(MAX_RULE_NODES - 1)
    )
    rule_set = RuleSet("max-size", RuleGroup("root", LogicOperator.AND, children))
    result = RuleEngine().evaluate(rule_set, {"x": 1.0})
    assert result.status is RuleStatus.PASS
    assert len(result.evaluations) == MAX_RULE_NODES


def test_rule_tree_above_node_limit_is_rejected() -> None:
    children = tuple(
        ScalarRule(f"r{i}", "x", CompareOperator.GTE, value=0.0)
        for i in range(MAX_RULE_NODES)
    )
    with pytest.raises(RuleValidationError, match="cannot exceed"):
        RuleSet("too-large", RuleGroup("root", LogicOperator.AND, children))


def test_rule_tree_depth_limit_is_enforced() -> None:
    node = ScalarRule("leaf", "x", CompareOperator.GTE, value=0.0)
    # One scalar leaf plus nested NOT groups. Exactly MAX_RULE_DEPTH total nodes is valid.
    for depth in range(1, MAX_RULE_DEPTH):
        node = RuleGroup(f"g{depth}", LogicOperator.NOT, (node,))
    RuleSet("max-depth", node)

    too_deep = RuleGroup("too-deep", LogicOperator.NOT, (node,))
    with pytest.raises(RuleValidationError, match="depth"):
        RuleSet("too-deep", too_deep)
