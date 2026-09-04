"""Framework-neutral A6 conditional-capture evaluation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ..control import MEASUREMENT_SLOTS
from ..errors import is_transport_error
from .artifacts import ArtifactAction, ArtifactCaptureResult, capture_artifacts

CONDITION_OPERATORS = (
    ">",
    ">=",
    "<",
    "<=",
    "inside",
    "outside",
    "abs_delta",
)
INVALID_MEASUREMENT_MAGNITUDE = 1.0e36
MIN_CONDITION_COOLDOWN_S = 1.0


@dataclass(frozen=True)
class ConditionalCaptureConfig:
    """Validated A6 condition and debounce/cooldown configuration."""

    slot: int
    operator: str
    threshold: float
    high: float | None = None
    consecutive_matches: int = 1
    cooldown_s: float = 30.0

    def __post_init__(self) -> None:
        if isinstance(self.slot, bool):
            raise ValueError("Condition measurement slot must be an integer from 1 to 8.")
        slot = int(self.slot)
        if slot not in MEASUREMENT_SLOTS:
            raise ValueError("Condition measurement slot must be between MEAS1 and MEAS8.")
        operator = str(self.operator).strip().lower()
        if operator not in CONDITION_OPERATORS:
            raise ValueError(f"Unsupported conditional operator: {self.operator!r}.")
        threshold = float(self.threshold)
        if not math.isfinite(threshold):
            raise ValueError("Condition threshold must be finite.")
        high = None if self.high is None else float(self.high)
        if high is not None and not math.isfinite(high):
            raise ValueError("Condition high limit must be finite.")
        if operator in {"inside", "outside"}:
            if high is None:
                raise ValueError("Inside/outside conditions require both low and high limits.")
            if threshold > high:
                raise ValueError("Condition low limit must not exceed the high limit.")
        if operator == "abs_delta" and threshold < 0:
            raise ValueError("Absolute-delta threshold must be non-negative.")
        matches = int(self.consecutive_matches)
        if isinstance(self.consecutive_matches, bool) or matches < 1:
            raise ValueError("Consecutive matches must be a positive integer.")
        cooldown = float(self.cooldown_s)
        if not math.isfinite(cooldown) or cooldown < MIN_CONDITION_COOLDOWN_S:
            raise ValueError(
                f"Conditional capture cooldown must be at least "
                f"{MIN_CONDITION_COOLDOWN_S:g} second."
            )
        object.__setattr__(self, "slot", slot)
        object.__setattr__(self, "operator", operator)
        object.__setattr__(self, "threshold", threshold)
        object.__setattr__(self, "high", high)
        object.__setattr__(self, "consecutive_matches", matches)
        object.__setattr__(self, "cooldown_s", cooldown)


@dataclass(frozen=True)
class ConditionEvaluation:
    """One condition evaluation result."""

    valid: bool
    matched: bool
    fire: bool
    value: float | None
    previous_value: float | None
    streak: int
    cooldown_remaining_s: float = 0.0
    error: str = ""


@dataclass(frozen=True)
class ConditionalPollResult:
    """Result from one serialized measurement/evaluate/capture poll."""

    evaluation: ConditionEvaluation
    artifacts: ArtifactCaptureResult | None = None

    @property
    def captured(self) -> bool:
        return bool(
            self.evaluation.fire
            and self.artifacts is not None
            and self.artifacts.success
        )


def parse_measurement_value(raw: Any) -> float:
    """Parse a DPO measurement response and reject invalid/sentinel values."""

    text = str(raw or "").strip()
    if not text:
        raise ValueError("Measurement value is empty.")
    token = text.split()[-1]
    value = float(token)
    if not math.isfinite(value) or abs(value) >= INVALID_MEASUREMENT_MAGNITUDE:
        raise ValueError(f"Measurement value is invalid: {token!r}.")
    return value


class ConditionalEvaluator:
    """Stateful debounce/cooldown evaluator for one A6 run."""

    def __init__(self, config: ConditionalCaptureConfig) -> None:
        self.config = config
        self._previous_value: float | None = None
        self._streak = 0
        self._last_capture_s: float | None = None

    @property
    def streak(self) -> int:
        return self._streak

    @property
    def previous_value(self) -> float | None:
        return self._previous_value

    def reset(self) -> None:
        self._previous_value = None
        self._streak = 0
        self._last_capture_s = None

    def invalidate(self, error: str) -> ConditionEvaluation:
        previous = self._previous_value
        self._previous_value = None
        self._streak = 0
        return ConditionEvaluation(
            valid=False,
            matched=False,
            fire=False,
            value=None,
            previous_value=previous,
            streak=0,
            error=str(error or "Invalid measurement value"),
        )

    def evaluate(self, raw: Any, *, now_s: float) -> ConditionEvaluation:
        try:
            value = parse_measurement_value(raw)
        except Exception as exc:  # noqa: BLE001 - invalid values are condition data.
            return self.invalidate(str(exc))

        now = float(now_s)
        if not math.isfinite(now):
            raise ValueError("Condition evaluation time must be finite.")

        previous = self._previous_value
        matched = self._matches(value, previous)
        self._previous_value = value
        if matched:
            self._streak = min(self._streak + 1, self.config.consecutive_matches)
        else:
            self._streak = 0

        cooldown_remaining = 0.0
        if self._last_capture_s is not None:
            cooldown_remaining = max(
                0.0,
                self.config.cooldown_s - (now - self._last_capture_s),
            )
        fire = self._streak >= self.config.consecutive_matches and cooldown_remaining <= 0.0
        if fire:
            self._last_capture_s = now
            self._streak = 0

        return ConditionEvaluation(
            valid=True,
            matched=matched,
            fire=fire,
            value=value,
            previous_value=previous,
            streak=self.config.consecutive_matches if fire else self._streak,
            cooldown_remaining_s=cooldown_remaining,
        )

    def _matches(self, value: float, previous: float | None) -> bool:
        operator = self.config.operator
        threshold = self.config.threshold
        if operator == ">":
            return value > threshold
        if operator == ">=":
            return value >= threshold
        if operator == "<":
            return value < threshold
        if operator == "<=":
            return value <= threshold
        if operator == "inside":
            assert self.config.high is not None
            return threshold <= value <= self.config.high
        if operator == "outside":
            assert self.config.high is not None
            return value < threshold or value > self.config.high
        if operator == "abs_delta":
            return previous is not None and abs(value - previous) > threshold
        raise RuntimeError(f"Unhandled conditional operator: {operator}")


def run_conditional_poll(
    scope: Any,
    evaluator: ConditionalEvaluator,
    *,
    now_s: float,
    action: ArtifactAction | str,
    image_path: str | None = None,
    csv_path: str | None = None,
) -> ConditionalPollResult:
    """Read one MEAS slot and capture selected artifacts when the condition fires."""

    try:
        raw = scope.read_measurement_value(evaluator.config.slot)
    except Exception as exc:  # noqa: BLE001 - transport errors propagate; invalid reads reset debounce.
        if is_transport_error(exc):
            raise
        return ConditionalPollResult(evaluator.invalidate(str(exc)))

    evaluation = evaluator.evaluate(raw, now_s=now_s)
    if not evaluation.fire:
        return ConditionalPollResult(evaluation)

    artifacts = capture_artifacts(
        scope,
        action,
        image_path=image_path,
        csv_path=csv_path,
    )
    return ConditionalPollResult(evaluation, artifacts)


__all__ = [
    "CONDITION_OPERATORS",
    "INVALID_MEASUREMENT_MAGNITUDE",
    "MIN_CONDITION_COOLDOWN_S",
    "ConditionEvaluation",
    "ConditionalCaptureConfig",
    "ConditionalEvaluator",
    "ConditionalPollResult",
    "parse_measurement_value",
    "run_conditional_poll",
]
