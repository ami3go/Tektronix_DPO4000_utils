"""Trigger-acquisition automation state models and fresh-Single wait helpers."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Protocol

from .periodic import AutomationEventToken, AutomationState, AutomationStatistics

MIN_TRIGGER_POLL_INTERVAL_S = 0.1
MAX_TRIGGER_POLL_INTERVAL_S = 10.0
MIN_TRIGGER_TIMEOUT_S = 1.0
MAX_TRIGGER_TIMEOUT_S = 604800.0
FRESH_TRIGGER_STATES = frozenset({"ARMED", "AUTO", "READY", "TRIGGER"})


class TriggerCancelSignal(Protocol):
    """Minimal cancellation interface used by worker-side trigger waits."""

    def is_set(self) -> bool: ...

    def wait(self, timeout: float) -> bool: ...


@dataclass(frozen=True)
class TriggerImageConfig:
    """Validated trigger-capture configuration."""

    poll_interval_s: float = 0.5
    rearm: bool = True
    timeout_s: float = 30.0

    def __post_init__(self) -> None:
        poll = float(self.poll_interval_s)
        if not math.isfinite(poll):
            raise ValueError("Poll interval must be finite.")
        if poll < MIN_TRIGGER_POLL_INTERVAL_S:
            raise ValueError(
                f"Poll interval must be at least {MIN_TRIGGER_POLL_INTERVAL_S:g} second."
            )
        if poll > MAX_TRIGGER_POLL_INTERVAL_S:
            raise ValueError(
                f"Poll interval must not exceed {MAX_TRIGGER_POLL_INTERVAL_S:g} seconds."
            )
        timeout = float(self.timeout_s)
        if not math.isfinite(timeout):
            raise ValueError("Trigger timeout must be finite.")
        if timeout < MIN_TRIGGER_TIMEOUT_S:
            raise ValueError(
                f"Trigger timeout must be at least {MIN_TRIGGER_TIMEOUT_S:g} second."
            )
        if timeout > MAX_TRIGGER_TIMEOUT_S:
            raise ValueError(
                f"Trigger timeout must not exceed {MAX_TRIGGER_TIMEOUT_S:g} seconds."
            )
        object.__setattr__(self, "poll_interval_s", poll)
        object.__setattr__(self, "timeout_s", timeout)


@dataclass(frozen=True)
class TriggerWaitResult:
    """Outcome returned by one worker-side fresh Single-acquisition wait."""

    completed: bool
    cancelled: bool = False
    timed_out: bool = False
    observed_fresh_state: bool = False
    acquisition_active: bool = False
    trigger_state: str = ""
    elapsed_s: float = 0.0


class TriggerImageController:
    """Qt-independent state/counter model for A2 trigger image capture."""

    def __init__(self) -> None:
        self.state = AutomationState.IDLE
        self.config: TriggerImageConfig | None = None
        self.statistics = AutomationStatistics()
        self._generation = 0
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def generation(self) -> int:
        """Current run generation used to reject stale worker completions."""
        return self._generation

    def start(self, config: TriggerImageConfig) -> None:
        if self.state is not AutomationState.IDLE:
            raise RuntimeError("Trigger automation is already active.")
        self._generation += 1
        self.config = config
        self.statistics = AutomationStatistics()
        self._busy = False
        self.state = AutomationState.RUNNING

    def pause(self) -> None:
        if self.state is AutomationState.RUNNING:
            self.state = AutomationState.PAUSED

    def resume(self) -> None:
        if self.state is AutomationState.PAUSED:
            self.state = AutomationState.RUNNING

    def stop(self) -> None:
        self._generation += 1
        self.state = AutomationState.IDLE
        self.config = None
        self._busy = False

    def begin_cycle(self) -> AutomationEventToken | None:
        if self.state is not AutomationState.RUNNING:
            return None
        if self._busy:
            self.statistics.skipped += 1
            return None
        self._busy = True
        self.statistics.attempted += 1
        return AutomationEventToken(self._generation, self.statistics.attempted)

    def cancel_cycle(self, token: AutomationEventToken) -> bool:
        if token.generation != self._generation:
            return False
        self._busy = False
        return True

    def finish_cycle(
        self,
        token: AutomationEventToken,
        *,
        success: bool,
        error: str = "",
    ) -> bool:
        if token.generation != self._generation:
            return False
        self._busy = False
        if success:
            self.statistics.succeeded += 1
            self.statistics.last_error = ""
        else:
            self.statistics.failed += 1
            self.statistics.last_error = str(error or "Trigger capture failed")
        return True


def trigger_acquisition_complete(*, acquisition_active: bool, trigger_state: str) -> bool:
    """Return True only for the documented stopped/saved single-acquisition state."""
    return not bool(acquisition_active) and str(trigger_state).strip().upper() == "SAVE"


def _fresh_state_observed(
    *,
    baseline_active: bool,
    baseline_trigger_state: str,
    acquisition_active: bool,
    trigger_state: str,
) -> bool:
    """Return True only for a changed post-arm active/armed state."""

    current_trigger = str(trigger_state).strip().upper()
    baseline_trigger = str(baseline_trigger_state).strip().upper()
    state_changed = (bool(acquisition_active), current_trigger) != (
        bool(baseline_active),
        baseline_trigger,
    )
    if not state_changed:
        return False
    return bool(acquisition_active) or current_trigger in FRESH_TRIGGER_STATES


def wait_for_fresh_single(
    scope: Any,
    cancel: TriggerCancelSignal | None,
    *,
    poll_interval_s: float = 0.5,
    timeout_s: float = 30.0,
) -> TriggerWaitResult:
    """Arm Single and wait for a *fresh* completed acquisition.

    The helper samples the pre-arm state, then requires observing a changed
    active/armed state after ``single_acquisition()`` before ``SAVE`` can count as
    completion. A stale pre-existing ``SAVE`` or ``READY`` state is therefore not
    sufficient. Timeout and cancellation both stop acquisition before returning.
    """

    config = TriggerImageConfig(
        poll_interval_s=poll_interval_s,
        rearm=False,
        timeout_s=timeout_s,
    )
    if cancel is not None and cancel.is_set():
        return TriggerWaitResult(completed=False, cancelled=True)

    baseline_active = bool(scope.get_acquisition_state())
    baseline_trigger = str(scope.get_trigger_state())
    scope.single_acquisition()

    started = time.monotonic()
    deadline = started + config.timeout_s
    last_active = baseline_active
    last_trigger_state = baseline_trigger
    observed_fresh = False

    while True:
        if cancel is not None and cancel.is_set():
            scope.stop_acquisition()
            return TriggerWaitResult(
                completed=False,
                cancelled=True,
                observed_fresh_state=observed_fresh,
                acquisition_active=last_active,
                trigger_state=last_trigger_state,
                elapsed_s=max(0.0, time.monotonic() - started),
            )

        last_active = bool(scope.get_acquisition_state())
        last_trigger_state = str(scope.get_trigger_state())
        if _fresh_state_observed(
            baseline_active=baseline_active,
            baseline_trigger_state=baseline_trigger,
            acquisition_active=last_active,
            trigger_state=last_trigger_state,
        ):
            observed_fresh = True

        if observed_fresh and trigger_acquisition_complete(
            acquisition_active=last_active,
            trigger_state=last_trigger_state,
        ):
            return TriggerWaitResult(
                completed=True,
                observed_fresh_state=True,
                acquisition_active=last_active,
                trigger_state=last_trigger_state,
                elapsed_s=max(0.0, time.monotonic() - started),
            )

        now = time.monotonic()
        if now >= deadline:
            scope.stop_acquisition()
            return TriggerWaitResult(
                completed=False,
                timed_out=True,
                observed_fresh_state=observed_fresh,
                acquisition_active=last_active,
                trigger_state=last_trigger_state,
                elapsed_s=max(0.0, now - started),
            )

        wait_s = min(config.poll_interval_s, max(0.0, deadline - now))
        if cancel is not None and cancel.wait(wait_s):
            scope.stop_acquisition()
            return TriggerWaitResult(
                completed=False,
                cancelled=True,
                observed_fresh_state=observed_fresh,
                acquisition_active=last_active,
                trigger_state=last_trigger_state,
                elapsed_s=max(0.0, time.monotonic() - started),
            )
        if cancel is None:
            time.sleep(wait_s)


__all__ = [
    "FRESH_TRIGGER_STATES",
    "MAX_TRIGGER_POLL_INTERVAL_S",
    "MAX_TRIGGER_TIMEOUT_S",
    "MIN_TRIGGER_POLL_INTERVAL_S",
    "MIN_TRIGGER_TIMEOUT_S",
    "TriggerCancelSignal",
    "TriggerImageConfig",
    "TriggerImageController",
    "TriggerWaitResult",
    "trigger_acquisition_complete",
    "wait_for_fresh_single",
]
