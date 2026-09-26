from __future__ import annotations

from collections import deque

import pytest

from dpo4000_utils.recipe import (
    Recipe,
    RecipeRunState,
    RecipeSequencer,
    RecipeStep,
    RecipeValidationError,
    RetryPolicy,
    recipe_from_mapping,
    recipe_to_mapping,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class Target:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.failures = deque()

    def set_channel_enabled(self, channel: int, enabled: bool) -> str:
        self.calls.append(("set_channel_enabled", (channel, enabled), {}))
        if self.failures:
            exc = self.failures.popleft()
            if exc is not None:
                raise exc
        return "ok"


def test_recipe_round_trip_mapping() -> None:
    recipe = Recipe(
        name="smoke",
        steps=(
            RecipeStep.call("set_channel_enabled", 1, True),
            RecipeStep.delay(0.25),
        ),
    )
    assert recipe_from_mapping(recipe_to_mapping(recipe)) == recipe


@pytest.mark.parametrize(
    "raw",
    [
        {"version": 2, "name": "x", "steps": [{"kind": "delay", "seconds": 1}]},
        {"name": "x", "steps": []},
        {"name": "x", "steps": [{"kind": "call", "method": "_private"}]},
        {"name": "x", "steps": [{"kind": "call", "method": "write;*RST"}]},
        {"name": "x", "steps": [{"kind": "delay", "seconds": float("nan")}]},
        {"name": "x", "steps": [{"kind": "delay", "seconds": -1}]},
        {"name": "x", "steps": [{"kind": "call", "method": "foo", "extra": 1}]},
    ],
)
def test_invalid_recipe_documents_rejected_before_execution(raw) -> None:
    with pytest.raises(RecipeValidationError):
        recipe_from_mapping(raw)


def test_delay_uses_absolute_deadline_and_exact_fake_time() -> None:
    clock = FakeClock()
    target = Target()
    recipe = Recipe("delay", (RecipeStep.delay(0.12),))
    result = RecipeSequencer(
        target,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        cancel_poll_s=0.05,
    ).run(recipe)
    assert result.state is RecipeRunState.COMPLETED
    assert result.duration_s == pytest.approx(0.12)
    assert sum(clock.sleeps) == pytest.approx(0.12)
    assert max(clock.sleeps) <= 0.05


def test_call_step_uses_public_target_method_and_returns_value() -> None:
    clock = FakeClock()
    target = Target()
    recipe = Recipe("call", (RecipeStep.call("set_channel_enabled", 2, True),))
    result = RecipeSequencer(target, monotonic=clock.monotonic, sleep=clock.sleep).run(recipe)
    assert result.state is RecipeRunState.COMPLETED
    assert target.calls == [("set_channel_enabled", (2, True), {})]
    assert result.steps[0].value == "ok"


def test_missing_public_method_fails_without_arbitrary_dispatch() -> None:
    target = Target()
    recipe = Recipe("bad", (RecipeStep.call("raw_scpi"),))
    result = RecipeSequencer(target).run(recipe)
    assert result.state is RecipeRunState.FAILED
    assert "RecipeValidationError" in (result.error or "")
    assert target.calls == []


def test_retry_schedule_is_bounded_and_deterministic() -> None:
    clock = FakeClock()
    target = Target()
    target.failures.extend([RuntimeError("one"), RuntimeError("two"), None])
    recipe = Recipe(
        "retry",
        (
            RecipeStep.call(
                "set_channel_enabled",
                1,
                True,
                retry=RetryPolicy(attempts=3, delay_s=0.1, backoff=2, max_delay_s=0.15),
            ),
        ),
    )
    result = RecipeSequencer(
        target,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        cancel_poll_s=1.0,
    ).run(recipe)
    assert result.state is RecipeRunState.COMPLETED
    assert result.steps[0].attempts == 3
    assert clock.sleeps == pytest.approx([0.1, 0.15])
    assert len(target.calls) == 3


def test_failure_stops_following_steps() -> None:
    target = Target()
    target.failures.append(RuntimeError("boom"))
    recipe = Recipe(
        "stop",
        (
            RecipeStep.call("set_channel_enabled", 1, True),
            RecipeStep.call("set_channel_enabled", 2, True),
        ),
    )
    result = RecipeSequencer(target).run(recipe)
    assert result.state is RecipeRunState.FAILED
    assert len(target.calls) == 1


def test_cancel_before_run_checkpoint_prevents_io() -> None:
    class CancelAtStartSequencer(RecipeSequencer):
        def _checkpoint(self) -> None:
            self.cancel()
            super()._checkpoint()

    target = Target()
    recipe = Recipe("cancel", (RecipeStep.call("set_channel_enabled", 1, True),))
    result = CancelAtStartSequencer(target).run(recipe)
    assert result.state is RecipeRunState.CANCELLED
    assert target.calls == []


def test_callbacks_receive_ordered_step_results() -> None:
    clock = FakeClock()
    target = Target()
    started: list[int] = []
    finished: list[int] = []
    recipe = Recipe(
        "callbacks",
        (
            RecipeStep.call("set_channel_enabled", 1, True),
            RecipeStep.delay(0.01),
        ),
    )
    result = RecipeSequencer(target, monotonic=clock.monotonic, sleep=clock.sleep).run(
        recipe,
        on_step_start=lambda index, _step: started.append(index),
        on_step_finish=lambda step_result: finished.append(step_result.index),
    )
    assert result.state is RecipeRunState.COMPLETED
    assert started == [0, 1]
    assert finished == [0, 1]


def test_retry_policy_validation() -> None:
    with pytest.raises(RecipeValidationError):
        RetryPolicy(attempts=0)
    with pytest.raises(RecipeValidationError):
        RetryPolicy(delay_s=-1)
    with pytest.raises(RecipeValidationError):
        RetryPolicy(backoff=0.5)
