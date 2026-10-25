"""Validated recipe model and deterministic A15 sequencer.

A15 deliberately executes public driver methods instead of accepting raw SCPI,
Python expressions, imports, or shell commands. The same engine is suitable for
DPO4000 Desk's serialized worker path and the future A25 headless runner.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
import inspect
import math
from pathlib import Path
import threading
import time
from typing import Any, Callable, Mapping, Sequence, Union

from .bus import BusConfig
from .control import (
    AcquisitionConfig,
    ChannelConfig,
    DisplayConfig,
    MathConfig,
    MeasurementConfig,
    SequenceTriggerConfig,
    TriggerConfig,
)
from .reference import ReferenceConfig
from .rules import (
    CompareOperator,
    RuleEngine,
    RuleSet,
    RuleStatus,
    RuleValidationError,
    ScalarRule,
    _flatten_value,
)

MAX_RECIPE_STEPS = 10_000
MAX_RETRY_ATTEMPTS = 100
MAX_REPEAT_COUNT = 10_000
MAX_REPEAT_DEPTH = 4
SUPPORTED_RECIPE_VERSIONS = (1, 2)
_CONDITION_FIELDS = ("input", "operator", "value", "low", "high", "reference", "tolerance")

# These public methods expose the transport/session lifecycle or accept arbitrary
# SCPI. Recipes must stay above that boundary.
RECIPE_DENIED_METHODS = frozenset(
    {
        "connect",
        "configure_session",
        "disconnect",
        "ensure_connected",
        "probe_scpi_query",
        "temporary_timeout",
    }
)

_CONFIG_TYPES: dict[str, type[Any]] = {
    "add_measurement": MeasurementConfig,
    "apply_display_settings": DisplayConfig,
    "configure_acquisition": AcquisitionConfig,
    "configure_bus": BusConfig,
    "configure_channel": ChannelConfig,
    "configure_math": MathConfig,
    "configure_reference": ReferenceConfig,
    "configure_sequence_trigger": SequenceTriggerConfig,
    "configure_trigger": TriggerConfig,
}


class RecipeValidationError(ValueError):
    """Raised when a recipe or step is invalid before instrument I/O."""


class RecipeCancelled(RuntimeError):
    """Raised internally when execution is cancelled."""


class StepKind(str, Enum):
    CALL = "call"
    DELAY = "delay"


class ConditionInvalidPolicy(str, Enum):
    """What to do when a step condition cannot be evaluated (missing/non-numeric input)."""

    FAIL = "fail"
    SKIP = "skip"


class RecipeRunState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 1
    delay_s: float = 0.0
    backoff: float = 1.0
    max_delay_s: float | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.attempts, bool)
            or not isinstance(self.attempts, int)
            or not 1 <= self.attempts <= MAX_RETRY_ATTEMPTS
        ):
            raise RecipeValidationError(
                f"retry attempts must be an integer from 1 to {MAX_RETRY_ATTEMPTS}"
            )
        for name, value in (("delay_s", self.delay_s), ("backoff", self.backoff)):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise RecipeValidationError(f"{name} must be a finite number")
        if self.delay_s < 0:
            raise RecipeValidationError("retry delay_s must be >= 0")
        if self.backoff < 1:
            raise RecipeValidationError("retry backoff must be >= 1")
        if self.max_delay_s is not None:
            if (
                isinstance(self.max_delay_s, bool)
                or not isinstance(self.max_delay_s, (int, float))
                or not math.isfinite(float(self.max_delay_s))
                or self.max_delay_s < 0
            ):
                raise RecipeValidationError(
                    "retry max_delay_s must be a finite number >= 0 or None"
                )

    def delay_for_retry(self, retry_index: int) -> float:
        if retry_index < 0:
            raise RecipeValidationError("retry index must be >= 0")
        try:
            value = float(self.delay_s) * (float(self.backoff) ** retry_index)
        except OverflowError:
            if self.max_delay_s is None:
                raise RecipeValidationError("retry backoff overflows") from None
            value = float(self.max_delay_s)
        if not math.isfinite(value):
            if self.max_delay_s is None:
                raise RecipeValidationError("retry backoff overflows")
            value = float(self.max_delay_s)
        if self.max_delay_s is not None:
            value = min(value, float(self.max_delay_s))
        return value


@dataclass(frozen=True)
class RecipeStep:
    kind: StepKind
    name: str
    method: str | None = None
    args: tuple[Any, ...] = ()
    kwargs: Mapping[str, Any] = field(default_factory=dict)
    delay_s: float = 0.0
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    when: ScalarRule | None = None
    when_invalid: ConditionInvalidPolicy = ConditionInvalidPolicy.FAIL

    @classmethod
    def call(
        cls,
        method: str,
        *args: Any,
        name: str | None = None,
        retry: RetryPolicy | None = None,
        when: ScalarRule | None = None,
        when_invalid: ConditionInvalidPolicy | str = ConditionInvalidPolicy.FAIL,
        **kwargs: Any,
    ) -> "RecipeStep":
        return cls(
            kind=StepKind.CALL,
            name=name or method,
            method=method,
            args=tuple(args),
            kwargs=dict(kwargs),
            retry=retry or RetryPolicy(),
            when=when,
            when_invalid=when_invalid,
        )

    @classmethod
    def delay(
        cls,
        seconds: float,
        *,
        name: str | None = None,
        when: ScalarRule | None = None,
        when_invalid: ConditionInvalidPolicy | str = ConditionInvalidPolicy.FAIL,
    ) -> "RecipeStep":
        if isinstance(seconds, (int, float)) and not isinstance(seconds, bool):
            display = f"{seconds:g}s"
        else:
            display = str(seconds)
        return cls(
            kind=StepKind.DELAY,
            name=name or f"Delay {display}",
            delay_s=seconds,
            when=when,
            when_invalid=when_invalid,
        )

    def __post_init__(self) -> None:
        if not isinstance(self.kind, StepKind):
            try:
                object.__setattr__(self, "kind", StepKind(self.kind))
            except (TypeError, ValueError) as exc:
                raise RecipeValidationError(
                    f"unsupported step kind: {self.kind!r}"
                ) from exc

        if not isinstance(self.name, str) or not self.name.strip():
            raise RecipeValidationError("step name must be non-empty")
        if self.when is not None and not isinstance(self.when, ScalarRule):
            raise RecipeValidationError("step condition must be a ScalarRule or None")
        if not isinstance(self.when_invalid, ConditionInvalidPolicy):
            try:
                object.__setattr__(self, "when_invalid", ConditionInvalidPolicy(self.when_invalid))
            except (TypeError, ValueError) as exc:
                raise RecipeValidationError(
                    f"unsupported condition on_invalid policy: {self.when_invalid!r}"
                ) from exc

        if self.kind is StepKind.CALL:
            if (
                not isinstance(self.method, str)
                or not self.method.isidentifier()
                or self.method.startswith("_")
            ):
                raise RecipeValidationError(
                    "call method must be a public Python identifier"
                )
            if self.method in RECIPE_DENIED_METHODS:
                raise RecipeValidationError(
                    f"method {self.method!r} is not available to recipes"
                )
            if self.delay_s != 0:
                raise RecipeValidationError("call step cannot define delay_s")
            if not isinstance(self.args, tuple):
                try:
                    object.__setattr__(self, "args", tuple(self.args))
                except TypeError as exc:
                    raise RecipeValidationError(
                        "call args must be iterable"
                    ) from exc
            if not isinstance(self.kwargs, Mapping):
                raise RecipeValidationError("call kwargs must be a mapping")
            if not isinstance(self.retry, RetryPolicy):
                raise RecipeValidationError("call retry must be a RetryPolicy")
        elif self.kind is StepKind.DELAY:
            if self.method is not None or self.args or self.kwargs:
                raise RecipeValidationError(
                    "delay step cannot define a method or arguments"
                )
            if (
                isinstance(self.delay_s, bool)
                or not isinstance(self.delay_s, (int, float))
                or not math.isfinite(float(self.delay_s))
                or self.delay_s < 0
            ):
                raise RecipeValidationError(
                    "delay_s must be a finite number >= 0"
                )
            if self.retry != RetryPolicy():
                raise RecipeValidationError("delay step does not support retries")


@dataclass(frozen=True)
class RepeatBlock:
    """Run ``steps`` ``count`` times. Expanded to plain steps before execution.

    Use a step ``when`` condition inside the block for "repeat until": once the
    condition stops passing, the remaining iterations are skipped without I/O.
    """

    count: int
    steps: tuple["RecipeItem", ...]
    name: str = "Repeat"

    def __post_init__(self) -> None:
        if (
            isinstance(self.count, bool)
            or not isinstance(self.count, int)
            or not 1 <= self.count <= MAX_REPEAT_COUNT
        ):
            raise RecipeValidationError(
                f"repeat count must be an integer from 1 to {MAX_REPEAT_COUNT}"
            )
        if not isinstance(self.name, str) or not self.name.strip():
            raise RecipeValidationError("repeat name must be non-empty")
        if not isinstance(self.steps, tuple):
            try:
                object.__setattr__(self, "steps", tuple(self.steps))
            except TypeError as exc:
                raise RecipeValidationError("repeat steps must be iterable") from exc
        if not self.steps:
            raise RecipeValidationError("repeat block must contain at least one step")
        if not all(isinstance(item, (RecipeStep, RepeatBlock)) for item in self.steps):
            raise RecipeValidationError(
                "repeat steps must be RecipeStep or RepeatBlock instances"
            )


RecipeItem = Union[RecipeStep, RepeatBlock]


def _expanded_count(items: Sequence[RecipeItem], depth: int) -> int:
    if depth > MAX_REPEAT_DEPTH:
        raise RecipeValidationError(f"repeat blocks cannot be nested deeper than {MAX_REPEAT_DEPTH}")
    total = 0
    for item in items:
        if isinstance(item, RepeatBlock):
            total += item.count * _expanded_count(item.steps, depth + 1)
        else:
            total += 1
        if total > MAX_RECIPE_STEPS:
            raise RecipeValidationError(
                f"recipe cannot expand to more than {MAX_RECIPE_STEPS} steps"
            )
    return total


def _expand(items: Sequence[RecipeItem], output: list[RecipeStep]) -> None:
    for item in items:
        if isinstance(item, RepeatBlock):
            for _iteration in range(item.count):
                _expand(item.steps, output)
        else:
            output.append(item)


def _uses_v2_features(items: Sequence[RecipeItem]) -> bool:
    for item in items:
        if isinstance(item, RepeatBlock):
            return True
        if item.when is not None:
            return True
    return False


@dataclass(frozen=True)
class Recipe:
    """A validated recipe.

    ``steps`` is always the flat, expanded execution list, so every consumer that
    iterates it (preflight, method allow/deny checks, GUI rows) sees every call.
    ``definition`` keeps the authored structure, including repeat blocks.
    """

    name: str
    steps: tuple[RecipeStep, ...]
    version: int = 1
    definition: tuple[RecipeItem, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise RecipeValidationError("recipe name must be non-empty")
        if isinstance(self.version, bool) or not isinstance(self.version, int):
            raise RecipeValidationError("recipe version must be an integer")
        if self.version not in SUPPORTED_RECIPE_VERSIONS:
            raise RecipeValidationError(f"unsupported recipe version: {self.version}")
        if not isinstance(self.steps, tuple):
            try:
                object.__setattr__(self, "steps", tuple(self.steps))
            except TypeError as exc:
                raise RecipeValidationError("recipe steps must be iterable") from exc
        if not self.steps:
            raise RecipeValidationError("recipe must contain at least one step")
        if not all(isinstance(step, (RecipeStep, RepeatBlock)) for step in self.steps):
            raise RecipeValidationError(
                "all recipe steps must be RecipeStep or RepeatBlock instances"
            )
        _expanded_count(self.steps, 1)
        definition = self.steps
        if self.version == 1 and _uses_v2_features(definition):
            object.__setattr__(self, "version", 2)
        expanded: list[RecipeStep] = []
        _expand(definition, expanded)
        object.__setattr__(self, "definition", definition)
        object.__setattr__(self, "steps", tuple(expanded))


@dataclass(frozen=True)
class StepResult:
    index: int
    name: str
    attempts: int
    started_s: float
    finished_s: float
    value: Any = None
    skipped: bool = False

    @property
    def duration_s(self) -> float:
        return self.finished_s - self.started_s


@dataclass(frozen=True)
class RecipeResult:
    recipe_name: str
    state: RecipeRunState
    started_s: float
    finished_s: float
    steps: tuple[StepResult, ...]
    error: str | None = None

    @property
    def duration_s(self) -> float:
        return self.finished_s - self.started_s


def _validate_json_value(value: Any, *, field_name: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RecipeValidationError(
                f"{field_name} contains a non-finite number"
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, field_name=f"{field_name}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RecipeValidationError(
                    f"{field_name} mapping keys must be strings"
                )
            _validate_json_value(item, field_name=f"{field_name}.{key}")
        return
    raise RecipeValidationError(
        f"{field_name} contains unsupported JSON value {type(value).__name__}"
    )


def _coerce_config_argument(
    method_name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    config_type = _CONFIG_TYPES.get(method_name)
    if config_type is None:
        return args, kwargs

    mutable_args = list(args)
    if mutable_args and isinstance(mutable_args[0], Mapping):
        try:
            mutable_args[0] = config_type(**dict(mutable_args[0]))
        except (TypeError, ValueError) as exc:
            raise RecipeValidationError(
                f"invalid {method_name} config: {exc}"
            ) from exc
    elif "config" in kwargs and isinstance(kwargs["config"], Mapping):
        try:
            kwargs["config"] = config_type(**dict(kwargs["config"]))
        except (TypeError, ValueError) as exc:
            raise RecipeValidationError(
                f"invalid {method_name} config: {exc}"
            ) from exc
    return tuple(mutable_args), kwargs


class _ConditionInvalid(RuntimeError):
    """Raised when a step condition is INVALID under the FAIL policy."""


def _record_condition_values(values: dict[str, Any], result: "StepResult") -> None:
    """Update the condition namespace; later steps with the same name win."""
    _flatten_value(values, f"step.{result.index}", result.value)
    _flatten_value(values, f"step.{result.name}", result.value)
    _flatten_value(values, result.name, result.value)


def _condition_passes(step: RecipeStep, values: Mapping[str, Any]) -> bool:
    """Return True to run the step, False to skip it."""
    if step.when is None:
        return True
    evaluation = RuleEngine().evaluate(RuleSet(f"when {step.name}", step.when), values)
    if evaluation.status is RuleStatus.PASS:
        return True
    if evaluation.status is RuleStatus.FAIL:
        return False
    if step.when_invalid is ConditionInvalidPolicy.SKIP:
        return False
    raise _ConditionInvalid(f"condition for step {step.name!r} is invalid: {evaluation.root.reason}")


class RecipeSequencer:
    """Execute validated recipes with pause, cancellation, and bounded retries."""

    def __init__(
        self,
        target: Any,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        cancel_poll_s: float = 0.05,
    ) -> None:
        if (
            isinstance(cancel_poll_s, bool)
            or not isinstance(cancel_poll_s, (int, float))
            or not math.isfinite(float(cancel_poll_s))
            or cancel_poll_s <= 0
        ):
            raise RecipeValidationError(
                "cancel_poll_s must be a positive finite number"
            )
        self._target = target
        self._monotonic = monotonic
        self._sleep = sleep
        self._cancel_poll_s = float(cancel_poll_s)
        self._cancel = threading.Event()
        self._resume = threading.Event()
        self._resume.set()
        self._state = RecipeRunState.IDLE
        self._lock = threading.Lock()

    @property
    def state(self) -> RecipeRunState:
        with self._lock:
            return self._state

    def cancel(self) -> None:
        self._cancel.set()
        self._resume.set()

    def pause(self) -> None:
        with self._lock:
            if self._state is RecipeRunState.RUNNING:
                self._state = RecipeRunState.PAUSED
                self._resume.clear()

    def resume(self) -> None:
        with self._lock:
            if self._state is RecipeRunState.PAUSED:
                self._state = RecipeRunState.RUNNING
                self._resume.set()

    def _set_state(self, state: RecipeRunState) -> None:
        with self._lock:
            self._state = state

    def _checkpoint(self) -> float:
        """Block while paused and return monotonic time spent paused."""
        if self._cancel.is_set():
            raise RecipeCancelled()

        paused_started: float | None = None
        while not self._resume.is_set():
            if self._cancel.is_set():
                raise RecipeCancelled()
            if paused_started is None:
                paused_started = self._monotonic()
            self._sleep(self._cancel_poll_s)

        if self._cancel.is_set():
            raise RecipeCancelled()
        if paused_started is None:
            return 0.0
        return max(0.0, self._monotonic() - paused_started)

    def _interruptible_delay(self, seconds: float) -> None:
        if seconds <= 0:
            self._checkpoint()
            return
        deadline = self._monotonic() + seconds
        while True:
            deadline += self._checkpoint()
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                return
            self._sleep(min(remaining, self._cancel_poll_s))

    def _resolve_method(self, method_name: str) -> Callable[..., Any]:
        if method_name in RECIPE_DENIED_METHODS:
            raise RecipeValidationError(
                f"method {method_name!r} is not available to recipes"
            )
        method = getattr(self._target, method_name, None)
        if method is None or not callable(method) or method_name.startswith("_"):
            raise RecipeValidationError(
                f"target has no public callable {method_name!r}"
            )
        return method

    def _prepare_calls(
        self,
        recipe: Recipe,
    ) -> dict[int, tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]]]:
        """Resolve and signature-check all calls before executing the first step."""
        prepared: dict[
            int,
            tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]],
        ] = {}
        for index, step in enumerate(recipe.steps):
            if step.kind is not StepKind.CALL:
                continue
            method_name = step.method or ""
            method = self._resolve_method(method_name)
            args, kwargs = _coerce_config_argument(
                method_name,
                tuple(step.args),
                dict(step.kwargs),
            )
            try:
                inspect.signature(method).bind(*args, **kwargs)
            except ValueError:
                # Some extension/builtin callables expose no inspectable signature.
                pass
            except TypeError as exc:
                raise RecipeValidationError(
                    f"invalid arguments for {method_name}: {exc}"
                ) from exc
            prepared[index] = (method, args, kwargs)
        return prepared

    def run(
        self,
        recipe: Recipe,
        *,
        on_step_start: Callable[[int, RecipeStep], None] | None = None,
        on_step_finish: Callable[[StepResult], None] | None = None,
    ) -> RecipeResult:
        if not isinstance(recipe, Recipe):
            raise RecipeValidationError("recipe must be a Recipe")
        if self.state in {RecipeRunState.RUNNING, RecipeRunState.PAUSED}:
            raise RuntimeError("sequencer is already running")

        # Preflight the entire recipe before the first operation. A malformed later
        # step must not leave a partially-applied run.
        try:
            prepared = self._prepare_calls(recipe)
        except Exception as exc:
            now = self._monotonic()
            self._set_state(RecipeRunState.FAILED)
            return RecipeResult(
                recipe.name,
                RecipeRunState.FAILED,
                now,
                now,
                (),
                error=f"{type(exc).__name__}: {exc}",
            )

        self._cancel.clear()
        self._resume.set()
        self._set_state(RecipeRunState.RUNNING)
        started = self._monotonic()
        results: list[StepResult] = []
        condition_values: dict[str, Any] = {}

        try:
            for index, step in enumerate(recipe.steps):
                self._checkpoint()
                if on_step_start is not None:
                    on_step_start(index, step)
                step_started = self._monotonic()
                attempts = 1
                value: Any = None

                if not _condition_passes(step, condition_values):
                    skipped = StepResult(
                        index=index,
                        name=step.name,
                        attempts=0,
                        started_s=step_started,
                        finished_s=self._monotonic(),
                        skipped=True,
                    )
                    results.append(skipped)
                    if on_step_finish is not None:
                        on_step_finish(skipped)
                    continue

                if step.kind is StepKind.DELAY:
                    self._interruptible_delay(float(step.delay_s))
                else:
                    method, args, kwargs = prepared[index]
                    for attempt_index in range(step.retry.attempts):
                        attempts = attempt_index + 1
                        self._checkpoint()
                        try:
                            value = method(*args, **kwargs)
                            break
                        except Exception:
                            if attempts >= step.retry.attempts:
                                raise
                            self._interruptible_delay(
                                step.retry.delay_for_retry(attempt_index)
                            )

                step_result = StepResult(
                    index=index,
                    name=step.name,
                    attempts=attempts,
                    started_s=step_started,
                    finished_s=self._monotonic(),
                    value=value,
                )
                results.append(step_result)
                _record_condition_values(condition_values, step_result)
                if on_step_finish is not None:
                    on_step_finish(step_result)
        except RecipeCancelled:
            finished = self._monotonic()
            self._set_state(RecipeRunState.CANCELLED)
            return RecipeResult(
                recipe.name,
                RecipeRunState.CANCELLED,
                started,
                finished,
                tuple(results),
            )
        except Exception as exc:
            finished = self._monotonic()
            self._set_state(RecipeRunState.FAILED)
            return RecipeResult(
                recipe.name,
                RecipeRunState.FAILED,
                started,
                finished,
                tuple(results),
                error=f"{type(exc).__name__}: {exc}",
            )

        finished = self._monotonic()
        self._set_state(RecipeRunState.COMPLETED)
        return RecipeResult(
            recipe.name,
            RecipeRunState.COMPLETED,
            started,
            finished,
            tuple(results),
        )


def _condition_from_mapping(raw: Any, *, step_name: str) -> tuple[ScalarRule, ConditionInvalidPolicy]:
    if not isinstance(raw, Mapping):
        raise RecipeValidationError("step when must be a mapping")
    unknown = set(raw) - set(_CONDITION_FIELDS) - {"on_invalid"}
    if unknown:
        raise RecipeValidationError(f"unknown when fields: {sorted(unknown)!r}")
    try:
        rule = ScalarRule(
            id=f"when:{step_name}",
            input=raw.get("input"),
            operator=CompareOperator(raw.get("operator")),
            value=raw.get("value"),
            low=raw.get("low"),
            high=raw.get("high"),
            reference=raw.get("reference"),
            tolerance=raw.get("tolerance"),
        )
        policy = ConditionInvalidPolicy(raw.get("on_invalid", ConditionInvalidPolicy.FAIL.value))
    except (RuleValidationError, TypeError, ValueError) as exc:
        raise RecipeValidationError(f"invalid when condition for {step_name!r}: {exc}") from exc
    return rule, policy


def _item_from_mapping(raw: Any, *, depth: int) -> RecipeItem:
    if not isinstance(raw, Mapping):
        raise RecipeValidationError("each step must be a mapping")
    kind = raw.get("kind")

    if kind == "repeat":
        if depth >= MAX_REPEAT_DEPTH:
            raise RecipeValidationError(
                f"repeat blocks cannot be nested deeper than {MAX_REPEAT_DEPTH}"
            )
        unknown_step = set(raw) - {"kind", "name", "count", "steps"}
        if unknown_step:
            raise RecipeValidationError(f"unknown repeat fields: {sorted(unknown_step)!r}")
        raw_children = raw.get("steps")
        if not isinstance(raw_children, Sequence) or isinstance(raw_children, (str, bytes)):
            raise RecipeValidationError("repeat steps must be a sequence")
        if len(raw_children) > MAX_RECIPE_STEPS:
            raise RecipeValidationError(
                f"repeat block cannot contain more than {MAX_RECIPE_STEPS} steps"
            )
        return RepeatBlock(
            count=raw.get("count"),
            steps=tuple(_item_from_mapping(child, depth=depth + 1) for child in raw_children),
            name=raw.get("name") or "Repeat",
        )

    when_raw = raw.get("when")

    if kind == StepKind.DELAY.value:
        unknown_step = set(raw) - {"kind", "name", "seconds", "when"}
        if unknown_step:
            raise RecipeValidationError(
                f"unknown delay fields: {sorted(unknown_step)!r}"
            )
        step = RecipeStep.delay(raw.get("seconds"), name=raw.get("name"))
        if when_raw is None:
            return step
        rule, policy = _condition_from_mapping(when_raw, step_name=step.name)
        return RecipeStep.delay(step.delay_s, name=step.name, when=rule, when_invalid=policy)

    if kind != StepKind.CALL.value:
        raise RecipeValidationError(f"unsupported step kind: {kind!r}")

    unknown_step = set(raw) - {
        "kind",
        "name",
        "method",
        "args",
        "kwargs",
        "retry",
        "when",
    }
    if unknown_step:
        raise RecipeValidationError(
            f"unknown call fields: {sorted(unknown_step)!r}"
        )

    retry_raw = raw.get("retry", {})
    if not isinstance(retry_raw, Mapping):
        raise RecipeValidationError("retry must be a mapping")
    retry_unknown = set(retry_raw) - {
        "attempts",
        "delay_s",
        "backoff",
        "max_delay_s",
    }
    if retry_unknown:
        raise RecipeValidationError(
            f"unknown retry fields: {sorted(retry_unknown)!r}"
        )
    try:
        retry = RetryPolicy(**dict(retry_raw))
    except TypeError as exc:
        raise RecipeValidationError(f"invalid retry policy: {exc}") from exc

    args = raw.get("args", ())
    kwargs = raw.get("kwargs", {})
    if not isinstance(args, Sequence) or isinstance(args, (str, bytes)):
        raise RecipeValidationError("step args must be a sequence")
    if not isinstance(kwargs, Mapping):
        raise RecipeValidationError("step kwargs must be a mapping")
    _validate_json_value(list(args), field_name="step args")
    _validate_json_value(dict(kwargs), field_name="step kwargs")

    method = raw.get("method")
    step_name = raw.get("name") or method
    when: ScalarRule | None = None
    policy = ConditionInvalidPolicy.FAIL
    if when_raw is not None:
        if not isinstance(step_name, str) or not step_name.strip():
            raise RecipeValidationError("step name must be non-empty")
        when, policy = _condition_from_mapping(when_raw, step_name=step_name)
    return RecipeStep(
        kind=StepKind.CALL,
        name=step_name,
        method=method,
        args=tuple(args),
        kwargs=dict(kwargs),
        retry=retry,
        when=when,
        when_invalid=policy,
    )


def recipe_from_mapping(data: Mapping[str, Any]) -> Recipe:
    """Load the stable recipe mapping used by Desk and the A25 headless runner.

    Version 1 documents contain only call/delay steps. Version 2 adds optional
    step ``when`` conditions and ``repeat`` blocks.
    """
    if not isinstance(data, Mapping):
        raise RecipeValidationError("recipe document must be a mapping")
    allowed = {"version", "name", "steps"}
    unknown = set(data) - allowed
    if unknown:
        raise RecipeValidationError(
            f"unknown recipe fields: {sorted(unknown)!r}"
        )

    version = data.get("version", 1)
    if isinstance(version, bool) or version not in SUPPORTED_RECIPE_VERSIONS:
        raise RecipeValidationError(f"unsupported recipe version: {version!r}")
    name = data.get("name")
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, Sequence) or isinstance(raw_steps, (str, bytes)):
        raise RecipeValidationError("steps must be a sequence")
    if len(raw_steps) > MAX_RECIPE_STEPS:
        raise RecipeValidationError(
            f"recipe cannot contain more than {MAX_RECIPE_STEPS} steps"
        )

    items = tuple(_item_from_mapping(raw, depth=1) for raw in raw_steps)
    if version == 1 and _uses_v2_features(items):
        raise RecipeValidationError(
            "when conditions and repeat blocks require recipe version 2"
        )
    return Recipe(name=name, version=version, steps=items)


def _mapping_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _mapping_value(item) for key, item in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_mapping_value(item) for item in value]
    if isinstance(value, list):
        return [_mapping_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _mapping_value(item) for key, item in value.items()}
    _validate_json_value(value, field_name="recipe value")
    return value


def _condition_to_mapping(step: RecipeStep) -> dict[str, Any]:
    rule = step.when
    assert rule is not None
    result: dict[str, Any] = {"input": rule.input, "operator": rule.operator.value}
    for name in _CONDITION_FIELDS[2:]:
        value = getattr(rule, name)
        if value is not None:
            result[name] = value
    if step.when_invalid is not ConditionInvalidPolicy.FAIL:
        result["on_invalid"] = step.when_invalid.value
    return result


def _item_to_mapping(item: RecipeItem) -> dict[str, Any]:
    if isinstance(item, RepeatBlock):
        return {
            "kind": "repeat",
            "name": item.name,
            "count": item.count,
            "steps": [_item_to_mapping(child) for child in item.steps],
        }
    if item.kind is StepKind.DELAY:
        mapping: dict[str, Any] = {
            "kind": "delay",
            "name": item.name,
            "seconds": float(item.delay_s),
        }
    else:
        retry = {
            "attempts": item.retry.attempts,
            "delay_s": float(item.retry.delay_s),
            "backoff": float(item.retry.backoff),
            "max_delay_s": (
                None
                if item.retry.max_delay_s is None
                else float(item.retry.max_delay_s)
            ),
        }
        mapping = {
            "kind": "call",
            "name": item.name,
            "method": item.method,
            "args": _mapping_value(item.args),
            "kwargs": _mapping_value(dict(item.kwargs)),
            "retry": retry,
        }
    if item.when is not None:
        mapping["when"] = _condition_to_mapping(item)
    return mapping


def recipe_to_mapping(recipe: Recipe) -> dict[str, Any]:
    """Return a JSON-compatible stable mapping that preserves repeat structure."""
    if not isinstance(recipe, Recipe):
        raise RecipeValidationError("recipe must be a Recipe")
    return {
        "version": recipe.version,
        "name": recipe.name,
        "steps": [_item_to_mapping(item) for item in recipe.definition],
    }


__all__ = [
    "MAX_RECIPE_STEPS",
    "MAX_REPEAT_COUNT",
    "MAX_REPEAT_DEPTH",
    "MAX_RETRY_ATTEMPTS",
    "RECIPE_DENIED_METHODS",
    "SUPPORTED_RECIPE_VERSIONS",
    "ConditionInvalidPolicy",
    "Recipe",
    "RecipeItem",
    "RecipeCancelled",
    "RecipeResult",
    "RecipeRunState",
    "RecipeSequencer",
    "RecipeStep",
    "RecipeValidationError",
    "RepeatBlock",
    "RetryPolicy",
    "StepKind",
    "StepResult",
    "recipe_from_mapping",
    "recipe_to_mapping",
]
