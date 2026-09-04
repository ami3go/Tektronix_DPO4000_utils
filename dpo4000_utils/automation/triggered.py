"""A2 Image-on-Trigger automation state models."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .periodic import AutomationEventToken, AutomationState, AutomationStatistics

MIN_TRIGGER_POLL_INTERVAL_S = 0.1
MAX_TRIGGER_POLL_INTERVAL_S = 10.0


@dataclass(frozen=True)
class TriggerImageConfig:
    """Validated trigger-capture configuration."""

    poll_interval_s: float = 0.5
    rearm: bool = True

    def __post_init__(self) -> None:
        value = float(self.poll_interval_s)
        if not math.isfinite(value):
            raise ValueError("Trigger poll interval must be finite.")
        if value < MIN_TRIGGER_POLL_INTERVAL_S:
            raise ValueError(
                f"Trigger poll interval must be at least {MIN_TRIGGER_POLL_INTERVAL_S:g} second."
            )
        if value > MAX_TRIGGER_POLL_INTERVAL_S:
            raise ValueError(
                f"Trigger poll interval must not exceed {MAX_TRIGGER_POLL_INTERVAL_S:g} seconds."
            )
        object.__setattr__(self, "poll_interval_s", value)


@dataclass(frozen=True)
class TriggerWaitResult:
    """Outcome returned by one worker-side single-acquisition wait."""

    completed: bool
    cancelled: bool = False
    acquisition_active: bool = False
    trigger_state: str = ""


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


__all__ = [
    "MAX_TRIGGER_POLL_INTERVAL_S",
    "MIN_TRIGGER_POLL_INTERVAL_S",
    "TriggerImageConfig",
    "TriggerImageController",
    "TriggerWaitResult",
    "trigger_acquisition_complete",
]
