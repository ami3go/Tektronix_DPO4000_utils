"""Validated recipe model and deterministic A15 sequencer.

The sequencer intentionally operates on public driver methods only.  It does not
construct arbitrary SCPI and is therefore safe to use from the Desk worker path
or a future headless runner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import threading
import time
from typing import Any, Callable, Iterable, Mapping, Sequence


class RecipeValidationError(ValueError):
    """Raised when a recipe or step is invalid before instrument I/O."""


class RecipeCancelled(RuntimeError):
    """Raised internally when execution is cancelled."""


class StepKind(str, Enum):
    CALL = "call"
    DELAY = "delay"


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
        if isinstance(self.attempts, bool) or not isinstance(self.attempts, int) or self.attempts < 1:
            raise RecipeValidationError("retry attempts must be an integer >= 1")
        for name, value in (("delay_s", self.delay_s), ("backoff", self.backoff)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise RecipeValidationError(f"{name} must be a finite number")
        if self.delay_s < 0:
            raise RecipeValidationError("retry delay_s must be >= 0")
        if self.backoff < 1:
            raise RecipeValidationError("retry backoff must be >= 1")
        if self.max_delay_s is not None:
            if isinstance(self.max_delay_s, bool) or not isinstance(self.max_delay_s, (int, float)):
                raise RecipeValidationError("retry max_delay_s must be a finite number or None")
            if not math.isfinite(float(self.max_delay_s)) or self.max_delay_s < 0:
                raise RecipeValidationError("retry max_delay_s must be >= 0")

    def delay_for_retry(self, retry_index: int) -> float:
        value = self.delay_s * (self.backoff ** retry_index)
        if self.max_delay_s is not None:
            value = min(value, self.max_delay_s)
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

    @classmethod
    def call(
        cls,
        method: str,
        *args: Any,
        name: str | None = None,
        retry: RetryPolicy | None = None,
        **kwargs: Any,
    ) -> "RecipeStep":
        return cls(
            kind=StepKind.CALL,
            name=name or method,
            method=method,
            args=tuple(args),
            kwargs=dict(kwargs),
            retry=retry or RetryPolicy(),
        )

    @classmethod
    def delay(cls, seconds: float, *, name: str | None = None) -> "RecipeStep":
        return cls(kind=StepKind.DELAY, name=name or f"Delay {seconds:g}s", delay_s=seconds)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise RecipeValidationError("step name must be non-empty")
        if self.kind is StepKind.CALL:
            if not isinstance(self.method, str) or not self.method.isidentifier() or self.method.startswith("_"):
                raise RecipeValidationError("call method must be a public Python identifier")
            if ";" in self.method or "\n" in self.method or "\r" in self.method:
                raise RecipeValidationError("invalid method name")
            if self.delay_s != 0:
                raise RecipeValidationError("call step cannot define delay_s")
        elif self.kind is StepKind.DELAY:
            if self.method is not None or self.args or self.kwargs:
                raise RecipeValidationError("delay step cannot define a method or arguments")
            if isinstance(self.delay_s, bool) or not isinstance(self.delay_s, (int, float)):
                raise RecipeValidationError("delay_s must be a finite number")
            if not math.isfinite(float(self.delay_s)) or self.delay_s < 0:
                raise RecipeValidationError("delay_s must be >= 0")
            if self.retry != RetryPolicy():
                raise RecipeValidationError("delay step does not support retries")
        else:
            raise RecipeValidationError(f"unsupported step kind: {self.kind!r}")


@dataclass(frozen=True)
class Recipe:
    name: str
    steps: tuple[RecipeStep, ...]
    version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise RecipeValidationError("recipe name must be non-empty")
        if self.version != 1:
            raise RecipeValidationError(f"unsupported recipe version: {self.version}")
        if not isinstance(self.steps, tuple):
            object.__setattr__(self, "steps", tuple(self.steps))
        if not self.steps:
            raise RecipeValidationError("recipe must contain at least one step")
        if not all(isinstance(step, RecipeStep) for step in self.steps):
            raise RecipeValidationError("all recipe steps must be RecipeStep instances")


@dataclass(frozen=True)
class StepResult:
    index: int
    name: str
    attempts: int
    started_s: float
    finished_s: float
    value: Any = None

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
        if isinstance(cancel_poll_s, bool) or not isinstance(cancel_poll_s, (int, float)):
            raise RecipeValidationError("cancel_poll_s must be a positive finite number")
        if not math.isfinite(float(cancel_poll_s)) or cancel_poll_s <= 0:
            raise RecipeValidationError("cancel_poll_s must be a positive finite number")
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

    def _checkpoint(self) -> None:
        if self._cancel.is_set():
            raise RecipeCancelled()
        while not self._resume.is_set():
            if self._cancel.is_set():
                raise RecipeCancelled()
            self._sleep(self._cancel_poll_s)

    def _interruptible_delay(self, seconds: float) -> None:
        if seconds <= 0:
            self._checkpoint()
            return
        deadline = self._monotonic() + seconds
        while True:
            self._checkpoint()
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                return
            self._sleep(min(remaining, self._cancel_poll_s))

    def _resolve_method(self, method_name: str) -> Callable[..., Any]:
        method = getattr(self._target, method_name, None)
        if method is None or not callable(method) or method_name.startswith("_"):
            raise RecipeValidationError(f"target has no public callable {method_name!r}")
        return method

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

        self._cancel.clear()
        self._resume.set()
        self._set_state(RecipeRunState.RUNNING)
        started = self._monotonic()
        results: list[StepResult] = []

        try:
            for index, step in enumerate(recipe.steps):
                self._checkpoint()
                if on_step_start is not None:
                    on_step_start(index, step)
                step_started = self._monotonic()
                attempts = 1
                value: Any = None
                if step.kind is StepKind.DELAY:
                    self._interruptible_delay(float(step.delay_s))
                else:
                    method = self._resolve_method(step.method or "")
                    for attempt_index in range(step.retry.attempts):
                        attempts = attempt_index + 1
                        self._checkpoint()
                        try:
                            value = method(*step.args, **dict(step.kwargs))
                            break
                        except Exception:
                            if attempts >= step.retry.attempts:
                                raise
                            self._interruptible_delay(step.retry.delay_for_retry(attempt_index))
                step_result = StepResult(
                    index=index,
                    name=step.name,
                    attempts=attempts,
                    started_s=step_started,
                    finished_s=self._monotonic(),
                    value=value,
                )
                results.append(step_result)
                if on_step_finish is not None:
                    on_step_finish(step_result)
        except RecipeCancelled:
            finished = self._monotonic()
            self._set_state(RecipeRunState.CANCELLED)
            return RecipeResult(recipe.name, RecipeRunState.CANCELLED, started, finished, tuple(results))
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
        return RecipeResult(recipe.name, RecipeRunState.COMPLETED, started, finished, tuple(results))


def recipe_from_mapping(data: Mapping[str, Any]) -> Recipe:
    """Load the stable v1 recipe mapping used by Desk and future A25 CLI."""
    if not isinstance(data, Mapping):
        raise RecipeValidationError("recipe document must be a mapping")
    allowed = {"version", "name", "steps"}
    unknown = set(data) - allowed
    if unknown:
        raise RecipeValidationError(f"unknown recipe fields: {sorted(unknown)!r}")
    version = data.get("version", 1)
    name = data.get("name")
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, Sequence) or isinstance(raw_steps, (str, bytes)):
        raise RecipeValidationError("steps must be a sequence")
    steps: list[RecipeStep] = []
    for raw in raw_steps:
        if not isinstance(raw, Mapping):
            raise RecipeValidationError("each step must be a mapping")
        kind = raw.get("kind")
        if kind == StepKind.DELAY.value:
            unknown_step = set(raw) - {"kind", "name", "seconds"}
            if unknown_step:
                raise RecipeValidationError(f"unknown delay fields: {sorted(unknown_step)!r}")
            steps.append(RecipeStep.delay(raw.get("seconds"), name=raw.get("name")))
        elif kind == StepKind.CALL.value:
            unknown_step = set(raw) - {"kind", "name", "method", "args", "kwargs", "retry"}
            if unknown_step:
                raise RecipeValidationError(f"unknown call fields: {sorted(unknown_step)!r}")
            retry_raw = raw.get("retry", {})
            if not isinstance(retry_raw, Mapping):
                raise RecipeValidationError("retry must be a mapping")
            retry_unknown = set(retry_raw) - {"attempts", "delay_s", "backoff", "max_delay_s"}
            if retry_unknown:
                raise RecipeValidationError(f"unknown retry fields: {sorted(retry_unknown)!r}")
            retry = RetryPolicy(**retry_raw)
            args = raw.get("args", ())
            kwargs = raw.get("kwargs", {})
            if not isinstance(args, Sequence) or isinstance(args, (str, bytes)):
                raise RecipeValidationError("step args must be a sequence")
            if not isinstance(kwargs, Mapping):
                raise RecipeValidationError("step kwargs must be a mapping")
            steps.append(
                RecipeStep.call(
                    raw.get("method"),
                    *args,
                    name=raw.get("name"),
                    retry=retry,
                    **dict(kwargs),
                )
            )
        else:
            raise RecipeValidationError(f"unsupported step kind: {kind!r}")
    return Recipe(name=name, version=version, steps=tuple(steps))


def recipe_to_mapping(recipe: Recipe) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    for step in recipe.steps:
        if step.kind is StepKind.DELAY:
            steps.append({"kind": "delay", "name": step.name, "seconds": step.delay_s})
        else:
            retry = {
                "attempts": step.retry.attempts,
                "delay_s": step.retry.delay_s,
                "backoff": step.retry.backoff,
                "max_delay_s": step.retry.max_delay_s,
            }
            steps.append(
                {
                    "kind": "call",
                    "name": step.name,
                    "method": step.method,
                    "args": list(step.args),
                    "kwargs": dict(step.kwargs),
                    "retry": retry,
                }
            )
    return {"version": recipe.version, "name": recipe.name, "steps": steps}
