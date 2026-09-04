"""Automation runtime models and scheduler state for DPO4000 Desk."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

MIN_PERIODIC_INTERVAL_S = 1.0
MAX_PERIODIC_INTERVAL_S = 7 * 24 * 60 * 60.0


class AutomationState(str, Enum):
    """User-visible automation state."""

    IDLE = "Idle"
    RUNNING = "Running"
    PAUSED = "Paused"


@dataclass(frozen=True)
class PeriodicImageConfig:
    """Validated A1 periodic-image configuration."""

    interval_s: float

    def __post_init__(self) -> None:
        value = float(self.interval_s)
        if not math.isfinite(value):
            raise ValueError("Automation interval must be finite.")
        if value < MIN_PERIODIC_INTERVAL_S:
            raise ValueError(
                f"Automation interval must be at least {MIN_PERIODIC_INTERVAL_S:g} second."
            )
        if value > MAX_PERIODIC_INTERVAL_S:
            raise ValueError("Automation interval must not exceed 7 days.")
        object.__setattr__(self, "interval_s", value)


@dataclass(frozen=True)
class AutomationEventToken:
    """Identity of one in-flight event, used to reject stale completions."""

    generation: int
    sequence: int


@dataclass
class AutomationStatistics:
    """Counters for the current periodic-image run."""

    attempted: int = 0
    succeeded: int = 0
    skipped: int = 0
    failed: int = 0
    last_error: str = ""


class PeriodicImageController:
    """Qt-independent A1 state machine.

    The GUI owns the actual timer. This class owns run state, event sequencing,
    overlap rejection and stale-completion protection so those rules can be unit
    tested without PySide6.
    """

    def __init__(self) -> None:
        self.state = AutomationState.IDLE
        self.config: PeriodicImageConfig | None = None
        self.statistics = AutomationStatistics()
        self._busy = False
        self._generation = 0

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def generation(self) -> int:
        return self._generation

    def start(self, config: PeriodicImageConfig) -> None:
        if self.state is not AutomationState.IDLE:
            raise RuntimeError("Automation is already active.")
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
        self._busy = False
        self.state = AutomationState.IDLE
        self.config = None

    def begin_event(self, *, force: bool = False) -> AutomationEventToken | None:
        """Reserve one event or reject it according to the no-overlap policy."""
        if not force and self.state is not AutomationState.RUNNING:
            return None
        if self._busy:
            self.statistics.skipped += 1
            return None
        self._busy = True
        self.statistics.attempted += 1
        return AutomationEventToken(self._generation, self.statistics.attempted)

    def finish_event(
        self,
        token: AutomationEventToken,
        *,
        success: bool,
        error: str = "",
    ) -> bool:
        """Finish an event; return False when completion belongs to an old run."""
        if token.generation != self._generation:
            return False
        self._busy = False
        if success:
            self.statistics.succeeded += 1
            self.statistics.last_error = ""
        else:
            self.statistics.failed += 1
            self.statistics.last_error = str(error or "Capture failed")
        return True

    def finish_skipped(self, token: AutomationEventToken, *, reason: str = "") -> bool:
        """Finish a reserved event without counting it as success or failure."""
        if token.generation != self._generation:
            return False
        self._busy = False
        self.statistics.skipped += 1
        self.statistics.last_error = str(reason) if reason else ""
        return True


def append_sequence(path: str | Path, sequence: int) -> Path:
    """Append a stable four-digit sequence before the extension."""
    candidate = Path(path)
    value = int(sequence)
    if value <= 0:
        raise ValueError("Automation sequence must be a positive integer.")
    return candidate.with_name(f"{candidate.stem}_{value:04d}{candidate.suffix}")


def collision_safe_path(path: str | Path, *, max_attempts: int = 9999) -> Path:
    """Return a non-existing path without silently overwriting an old artifact."""
    candidate = Path(path)
    if not candidate.exists():
        return candidate
    for index in range(1, int(max_attempts) + 1):
        alternate = candidate.with_name(f"{candidate.stem}_{index:03d}{candidate.suffix}")
        if not alternate.exists():
            return alternate
    raise FileExistsError(f"Could not allocate a unique automation output path for {candidate}.")


__all__ = [
    "AutomationEventToken",
    "AutomationState",
    "AutomationStatistics",
    "MAX_PERIODIC_INTERVAL_S",
    "MIN_PERIODIC_INTERVAL_S",
    "PeriodicImageConfig",
    "PeriodicImageController",
    "append_sequence",
    "collision_safe_path",
]
