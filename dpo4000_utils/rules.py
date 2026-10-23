"""GUI-independent deterministic A16 pass/fail rule engine.

The engine evaluates numeric measurements, recipe values, or calculated scalars.
It deliberately owns no instrument I/O and never evaluates Python expressions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any, Mapping, Sequence

MAX_RULE_NODES = 10_000
MAX_RULE_DEPTH = 64


class RuleValidationError(ValueError):
    """Raised when a rule document is structurally invalid."""


class RuleStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INVALID = "INVALID"


class CompareOperator(str, Enum):
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "=="
    NE = "!="
    INSIDE = "inside"
    OUTSIDE = "outside"
    ABS_DELTA_LTE = "abs_delta<="
    REL_DELTA_LTE = "rel_delta<="


class LogicOperator(str, Enum):
    AND = "AND"
    OR = "OR"
    NOT = "NOT"


def _finite_number(value: Any, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuleValidationError(f"{field_name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise RuleValidationError(f"{field_name} must be a finite number")
    return number


@dataclass(frozen=True)
class ScalarRule:
    id: str
    input: str
    operator: CompareOperator
    value: float | None = None
    low: float | None = None
    high: float | None = None
    reference: float | None = None
    tolerance: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise RuleValidationError("rule id must be non-empty")
        if not isinstance(self.input, str) or not self.input.strip():
            raise RuleValidationError("rule input must be non-empty")
        if not isinstance(self.operator, CompareOperator):
            try:
                object.__setattr__(self, "operator", CompareOperator(self.operator))
            except (TypeError, ValueError) as exc:
                raise RuleValidationError(
                    f"unsupported compare operator: {self.operator!r}"
                ) from exc

        simple = {
            CompareOperator.GT,
            CompareOperator.GTE,
            CompareOperator.LT,
            CompareOperator.LTE,
            CompareOperator.EQ,
            CompareOperator.NE,
        }
        if self.operator in simple:
            if self.value is None:
                raise RuleValidationError(f"operator {self.operator.value} requires value")
            object.__setattr__(self, "value", _finite_number(self.value, field_name="value"))
            self._reject_unused("low", self.low, "high", self.high, "reference", self.reference, "tolerance", self.tolerance)
            return

        if self.operator in {CompareOperator.INSIDE, CompareOperator.OUTSIDE}:
            if self.low is None or self.high is None:
                raise RuleValidationError(f"operator {self.operator.value} requires low and high")
            low = _finite_number(self.low, field_name="low")
            high = _finite_number(self.high, field_name="high")
            if low > high:
                raise RuleValidationError("low must be <= high")
            object.__setattr__(self, "low", low)
            object.__setattr__(self, "high", high)
            self._reject_unused("value", self.value, "reference", self.reference, "tolerance", self.tolerance)
            return

        if self.reference is None or self.tolerance is None:
            raise RuleValidationError(
                f"operator {self.operator.value} requires reference and tolerance"
            )
        reference = _finite_number(self.reference, field_name="reference")
        tolerance = _finite_number(self.tolerance, field_name="tolerance")
        if tolerance < 0:
            raise RuleValidationError("tolerance must be >= 0")
        object.__setattr__(self, "reference", reference)
        object.__setattr__(self, "tolerance", tolerance)
        self._reject_unused("value", self.value, "low", self.low, "high", self.high)

    @staticmethod
    def _reject_unused(*items: Any) -> None:
        for index in range(0, len(items), 2):
            name = items[index]
            value = items[index + 1]
            if value is not None:
                raise RuleValidationError(f"field {name} is not valid for this operator")


@dataclass(frozen=True)
class RuleGroup:
    id: str
    logic: LogicOperator
    children: tuple["RuleNode", ...]

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise RuleValidationError("group id must be non-empty")
        if not isinstance(self.logic, LogicOperator):
            try:
                object.__setattr__(self, "logic", LogicOperator(str(self.logic).upper()))
            except (TypeError, ValueError) as exc:
                raise RuleValidationError(f"unsupported logic operator: {self.logic!r}") from exc
        if not isinstance(self.children, tuple):
            object.__setattr__(self, "children", tuple(self.children))
        if not self.children:
            raise RuleValidationError("rule group must contain at least one child")
        if self.logic is LogicOperator.NOT and len(self.children) != 1:
            raise RuleValidationError("NOT group must contain exactly one child")
        if not all(isinstance(item, (ScalarRule, RuleGroup)) for item in self.children):
            raise RuleValidationError("group children must be rules or groups")


RuleNode = ScalarRule | RuleGroup


@dataclass(frozen=True)
class RuleSet:
    name: str
    root: RuleNode
    version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise RuleValidationError("rule-set name must be non-empty")
        if self.version != 1 or isinstance(self.version, bool):
            raise RuleValidationError(f"unsupported rule-set version: {self.version!r}")
        if not isinstance(self.root, (ScalarRule, RuleGroup)):
            raise RuleValidationError("rule-set root must be a rule or group")
        ids: set[str] = set()
        count = 0

        def visit(node: RuleNode, depth: int) -> None:
            nonlocal count
            if depth > MAX_RULE_DEPTH:
                raise RuleValidationError(
                    f"rule tree cannot exceed depth {MAX_RULE_DEPTH}"
                )
            count += 1
            if count > MAX_RULE_NODES:
                raise RuleValidationError(
                    f"rule tree cannot exceed {MAX_RULE_NODES} nodes"
                )
            if node.id in ids:
                raise RuleValidationError(f"duplicate rule id: {node.id!r}")
            ids.add(node.id)
            if isinstance(node, RuleGroup):
                for child in node.children:
                    visit(child, depth + 1)

        visit(self.root, 1)


@dataclass(frozen=True)
class RuleEvaluation:
    rule_id: str
    status: RuleStatus
    timestamp: str
    actual: float | None = None
    expected: Mapping[str, Any] = field(default_factory=dict)
    reason: str = ""
    children: tuple["RuleEvaluation", ...] = ()


@dataclass(frozen=True)
class RuleSetResult:
    name: str
    status: RuleStatus
    timestamp: str
    root: RuleEvaluation

    @property
    def evaluations(self) -> tuple[RuleEvaluation, ...]:
        items: list[RuleEvaluation] = []

        def visit(item: RuleEvaluation) -> None:
            items.append(item)
            for child in item.children:
                visit(child)

        visit(self.root)
        return tuple(items)


def _timestamp(value: datetime | str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str) and value.strip():
        return value
    raise RuleValidationError("timestamp must be datetime, non-empty string, or None")


def _actual_number(values: Mapping[str, Any], key: str) -> tuple[float | None, str | None]:
    if key not in values:
        return None, f"input {key!r} is missing"
    raw = values[key]
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None, f"input {key!r} is not numeric"
    actual = float(raw)
    if not math.isfinite(actual):
        return None, f"input {key!r} is not finite"
    return actual, None


def _expected(rule: ScalarRule) -> dict[str, Any]:
    result: dict[str, Any] = {"operator": rule.operator.value}
    for name in ("value", "low", "high", "reference", "tolerance"):
        value = getattr(rule, name)
        if value is not None:
            result[name] = value
    return result


def _evaluate_scalar(rule: ScalarRule, values: Mapping[str, Any], timestamp: str) -> RuleEvaluation:
    actual, error = _actual_number(values, rule.input)
    expected = _expected(rule)
    if error is not None or actual is None:
        return RuleEvaluation(
            rule.id,
            RuleStatus.INVALID,
            timestamp,
            actual=None,
            expected=expected,
            reason=error or "input unavailable",
        )

    op = rule.operator
    passed: bool
    if op is CompareOperator.GT:
        passed = actual > float(rule.value)
    elif op is CompareOperator.GTE:
        passed = actual >= float(rule.value)
    elif op is CompareOperator.LT:
        passed = actual < float(rule.value)
    elif op is CompareOperator.LTE:
        passed = actual <= float(rule.value)
    elif op is CompareOperator.EQ:
        passed = actual == float(rule.value)
    elif op is CompareOperator.NE:
        passed = actual != float(rule.value)
    elif op is CompareOperator.INSIDE:
        passed = float(rule.low) <= actual <= float(rule.high)
    elif op is CompareOperator.OUTSIDE:
        passed = actual < float(rule.low) or actual > float(rule.high)
    elif op is CompareOperator.ABS_DELTA_LTE:
        passed = abs(actual - float(rule.reference)) <= float(rule.tolerance)
    else:
        reference = float(rule.reference)
        if reference == 0.0:
            return RuleEvaluation(
                rule.id,
                RuleStatus.INVALID,
                timestamp,
                actual=actual,
                expected=expected,
                reason="relative delta reference cannot be zero",
            )
        passed = abs(actual - reference) / abs(reference) <= float(rule.tolerance)

    return RuleEvaluation(
        rule.id,
        RuleStatus.PASS if passed else RuleStatus.FAIL,
        timestamp,
        actual=actual,
        expected=expected,
        reason="condition satisfied" if passed else "condition not satisfied",
    )


def _evaluate_node(node: RuleNode, values: Mapping[str, Any], timestamp: str) -> RuleEvaluation:
    if isinstance(node, ScalarRule):
        return _evaluate_scalar(node, values, timestamp)

    children = tuple(_evaluate_node(child, values, timestamp) for child in node.children)
    statuses = tuple(child.status for child in children)
    if node.logic is LogicOperator.AND:
        if RuleStatus.FAIL in statuses:
            status = RuleStatus.FAIL
        elif RuleStatus.INVALID in statuses:
            status = RuleStatus.INVALID
        else:
            status = RuleStatus.PASS
    elif node.logic is LogicOperator.OR:
        if RuleStatus.PASS in statuses:
            status = RuleStatus.PASS
        elif RuleStatus.INVALID in statuses:
            status = RuleStatus.INVALID
        else:
            status = RuleStatus.FAIL
    else:
        child = children[0]
        if child.status is RuleStatus.PASS:
            status = RuleStatus.FAIL
        elif child.status is RuleStatus.FAIL:
            status = RuleStatus.PASS
        else:
            status = RuleStatus.INVALID

    return RuleEvaluation(
        node.id,
        status,
        timestamp,
        expected={"logic": node.logic.value},
        reason=f"{node.logic.value} group evaluated to {status.value}",
        children=children,
    )


class RuleEngine:
    """Evaluate a validated rule set against caller-provided scalar values."""

    def evaluate(
        self,
        rule_set: RuleSet,
        values: Mapping[str, Any],
        *,
        timestamp: datetime | str | None = None,
    ) -> RuleSetResult:
        if not isinstance(rule_set, RuleSet):
            raise RuleValidationError("rule_set must be a RuleSet")
        if not isinstance(values, Mapping):
            raise RuleValidationError("values must be a mapping")
        stamp = _timestamp(timestamp)
        root = _evaluate_node(rule_set.root, values, stamp)
        return RuleSetResult(rule_set.name, root.status, stamp, root)


def _node_from_mapping(data: Mapping[str, Any]) -> RuleNode:
    if not isinstance(data, Mapping):
        raise RuleValidationError("rule node must be a mapping")
    node_type = data.get("type")
    if node_type == "compare":
        allowed = {
            "type", "id", "input", "operator", "value", "low", "high",
            "reference", "tolerance",
        }
        unknown = set(data) - allowed
        if unknown:
            raise RuleValidationError(f"unknown compare fields: {sorted(unknown)!r}")
        try:
            return ScalarRule(
                id=data.get("id"),
                input=data.get("input"),
                operator=CompareOperator(data.get("operator")),
                value=data.get("value"),
                low=data.get("low"),
                high=data.get("high"),
                reference=data.get("reference"),
                tolerance=data.get("tolerance"),
            )
        except (TypeError, ValueError) as exc:
            if isinstance(exc, RuleValidationError):
                raise
            raise RuleValidationError(f"invalid compare rule: {exc}") from exc

    if node_type == "group":
        allowed = {"type", "id", "logic", "children"}
        unknown = set(data) - allowed
        if unknown:
            raise RuleValidationError(f"unknown group fields: {sorted(unknown)!r}")
        raw_children = data.get("children")
        if not isinstance(raw_children, Sequence) or isinstance(raw_children, (str, bytes)):
            raise RuleValidationError("group children must be a sequence")
        try:
            logic = LogicOperator(str(data.get("logic")).upper())
        except ValueError as exc:
            raise RuleValidationError(f"invalid group logic: {data.get('logic')!r}") from exc
        return RuleGroup(
            id=data.get("id"),
            logic=logic,
            children=tuple(_node_from_mapping(item) for item in raw_children),
        )

    raise RuleValidationError(f"unsupported rule node type: {node_type!r}")


def rule_set_from_mapping(data: Mapping[str, Any]) -> RuleSet:
    if not isinstance(data, Mapping):
        raise RuleValidationError("rule-set document must be a mapping")
    allowed = {"version", "name", "root"}
    unknown = set(data) - allowed
    if unknown:
        raise RuleValidationError(f"unknown rule-set fields: {sorted(unknown)!r}")
    root = data.get("root")
    if not isinstance(root, Mapping):
        raise RuleValidationError("rule-set root must be a mapping")
    return RuleSet(
        name=data.get("name"),
        version=data.get("version", 1),
        root=_node_from_mapping(root),
    )


def _node_to_mapping(node: RuleNode) -> dict[str, Any]:
    if isinstance(node, ScalarRule):
        result: dict[str, Any] = {
            "type": "compare",
            "id": node.id,
            "input": node.input,
            "operator": node.operator.value,
        }
        for name in ("value", "low", "high", "reference", "tolerance"):
            value = getattr(node, name)
            if value is not None:
                result[name] = value
        return result
    return {
        "type": "group",
        "id": node.id,
        "logic": node.logic.value,
        "children": [_node_to_mapping(child) for child in node.children],
    }


def rule_set_to_mapping(rule_set: RuleSet) -> dict[str, Any]:
    if not isinstance(rule_set, RuleSet):
        raise RuleValidationError("rule_set must be a RuleSet")
    return {
        "version": rule_set.version,
        "name": rule_set.name,
        "root": _node_to_mapping(rule_set.root),
    }


def _flatten_value(output: dict[str, Any], prefix: str, value: Any) -> None:
    output[prefix] = value
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, Mapping):
        for key, item in value.items():
            _flatten_value(output, f"{prefix}.{key}", item)


def recipe_result_values(result: Any) -> dict[str, Any]:
    """Expose completed A15 step values as named A16 inputs.

    Every step is available as ``step.<index>`` and ``step.<name>``. A unique
    step name is also exposed directly, so a recipe step named ``MEAS1`` can be
    referenced by a rule input named ``MEAS1``. Dataclass/mapping values are
    recursively flattened with dot-separated field names.
    """
    steps = getattr(result, "steps", None)
    if not isinstance(steps, tuple):
        raise RuleValidationError("result must expose a tuple of recipe steps")

    counts: dict[str, int] = {}
    for step in steps:
        name = str(getattr(step, "name", ""))
        counts[name] = counts.get(name, 0) + 1

    values: dict[str, Any] = {}
    for step in steps:
        index = getattr(step, "index", None)
        name = str(getattr(step, "name", ""))
        value = getattr(step, "value", None)
        _flatten_value(values, f"step.{index}", value)
        _flatten_value(values, f"step.{name}", value)
        if name and counts.get(name) == 1:
            _flatten_value(values, name, value)
    return values


__all__ = [
    "CompareOperator",
    "LogicOperator",
    "MAX_RULE_DEPTH",
    "MAX_RULE_NODES",
    "RuleEngine",
    "RuleEvaluation",
    "RuleGroup",
    "RuleNode",
    "RuleSet",
    "RuleSetResult",
    "RuleStatus",
    "RuleValidationError",
    "ScalarRule",
    "recipe_result_values",
    "rule_set_from_mapping",
    "rule_set_to_mapping",
]
