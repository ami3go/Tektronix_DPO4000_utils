from __future__ import annotations

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
    rule_set_from_mapping,
    rule_set_to_mapping,
)


def test_unit_is_carried_into_every_scalar_evaluation_status() -> None:
    rules = RuleSet(
        "units",
        RuleGroup(
            "all",
            LogicOperator.AND,
            (
                ScalarRule("pass", "MEAS1", CompareOperator.GTE, value=4.95, unit="V"),
                ScalarRule("fail", "MEAS2", CompareOperator.LT, value=1.0, unit="Hz"),
                ScalarRule("missing", "MEAS3", CompareOperator.GT, value=0.0, unit="s"),
                ScalarRule(
                    "zero-ref",
                    "MEAS1",
                    CompareOperator.REL_DELTA_LTE,
                    reference=0.0,
                    tolerance=0.1,
                    unit="V",
                ),
            ),
        ),
    )
    result = RuleEngine().evaluate(rules, {"MEAS1": 5.0, "MEAS2": 2.0})
    by_id = {item.rule_id: item for item in result.evaluations}
    assert (by_id["pass"].status, by_id["pass"].unit) == (RuleStatus.PASS, "V")
    assert (by_id["fail"].status, by_id["fail"].unit) == (RuleStatus.FAIL, "Hz")
    assert (by_id["missing"].status, by_id["missing"].unit) == (RuleStatus.INVALID, "s")
    assert (by_id["zero-ref"].status, by_id["zero-ref"].unit) == (RuleStatus.INVALID, "V")
    assert by_id["all"].unit is None


def test_unit_is_optional_and_blank_means_none() -> None:
    assert ScalarRule("r", "MEAS1", CompareOperator.GT, value=0.0).unit is None
    assert ScalarRule("r", "MEAS1", CompareOperator.GT, value=0.0, unit="  ").unit is None
    assert ScalarRule("r", "MEAS1", CompareOperator.GT, value=0.0, unit=" mV ").unit == "mV"


@pytest.mark.parametrize("unit", [5, b"V", "V\n", "x" * 33])
def test_invalid_units_are_rejected(unit) -> None:
    with pytest.raises(RuleValidationError):
        ScalarRule("r", "MEAS1", CompareOperator.GT, value=0.0, unit=unit)


def test_unit_round_trips_through_mapping_and_old_documents_still_load() -> None:
    rules = RuleSet("rt", ScalarRule("r", "MEAS1", CompareOperator.INSIDE, low=1.0, high=2.0, unit="A"))
    mapping = rule_set_to_mapping(rules)
    assert mapping["root"]["unit"] == "A"
    assert rule_set_from_mapping(mapping) == rules

    legacy = {
        "version": 1,
        "name": "legacy",
        "root": {"type": "compare", "id": "r", "input": "MEAS1", "operator": ">", "value": 0.0},
    }
    loaded = rule_set_from_mapping(legacy)
    assert loaded.root.unit is None
    assert "unit" not in rule_set_to_mapping(loaded)["root"]
