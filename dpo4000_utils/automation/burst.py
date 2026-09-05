"""Framework-neutral A7 burst event execution."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import (
    ArtifactAction,
    ArtifactCaptureResult,
    capture_artifacts,
    normalize_artifact_action,
)
from .bundle import CancelSignal
from .periodic import MAX_PERIODIC_INTERVAL_S
from .triggered import TriggerImageConfig, wait_for_fresh_single

MIN_BURST_DELAY_S = 0.0


@dataclass(frozen=True)
class BurstConfig:
    """Validated A7 finite-burst configuration."""

    count: int
    delay_s: float
    action: ArtifactAction | str = ArtifactAction.IMAGE
    single_acquisition: bool = False
    poll_interval_s: float = 0.5
    trigger_timeout_s: float = 30.0

    def __post_init__(self) -> None:
        if isinstance(self.count, bool):
            raise ValueError("Burst count must be a positive integer.")
        try:
            numeric_count = float(self.count)
            count = int(self.count)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Burst count must be a positive integer.") from exc
        if not math.isfinite(numeric_count) or numeric_count != float(count):
            raise ValueError("Burst count must be a positive integer.")
        if count < 1:
            raise ValueError("Burst count must be a positive integer.")
        if count > 1_000_000:
            raise ValueError("Burst count must not exceed 1,000,000 events.")
        delay = float(self.delay_s)
        if not math.isfinite(delay):
            raise ValueError("Burst delay must be finite.")
        if delay < MIN_BURST_DELAY_S:
            raise ValueError("Burst delay must be non-negative.")
        if delay > MAX_PERIODIC_INTERVAL_S:
            raise ValueError("Burst delay must not exceed 7 days.")
        action = normalize_artifact_action(self.action)
        if not isinstance(self.single_acquisition, bool):
            raise ValueError("Burst Single acquisition setting must be boolean.")
        trigger_config = TriggerImageConfig(
            poll_interval_s=float(self.poll_interval_s),
            rearm=False,
            timeout_s=float(self.trigger_timeout_s),
        )
        object.__setattr__(self, "count", count)
        object.__setattr__(self, "delay_s", delay)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "poll_interval_s", trigger_config.poll_interval_s)
        object.__setattr__(self, "trigger_timeout_s", trigger_config.timeout_s)


@dataclass(frozen=True)
class BurstEventResult:
    """Result from one A7 burst event."""

    cancelled: bool
    timed_out: bool = False
    observed_fresh_state: bool = False
    acquisition_active: bool | None = None
    trigger_state: str = ""
    artifacts: ArtifactCaptureResult | None = None

    @property
    def success(self) -> bool:
        return bool(
            not self.cancelled
            and not self.timed_out
            and self.artifacts is not None
            and self.artifacts.success
        )


def _wait_result(
    *,
    cancelled: bool,
    timed_out: bool,
    observed_fresh_state: bool,
    acquisition_active: bool | None,
    trigger_state: str,
) -> BurstEventResult:
    return BurstEventResult(
        cancelled=cancelled,
        timed_out=timed_out,
        observed_fresh_state=observed_fresh_state,
        acquisition_active=acquisition_active,
        trigger_state=trigger_state,
    )


def run_burst_event(
    scope: Any,
    cancel: CancelSignal,
    config: BurstConfig,
    *,
    image_path: str | Path | None = None,
    csv_path: str | Path | None = None,
) -> BurstEventResult:
    """Execute one finite-burst event through public driver APIs only.

    When ``single_acquisition`` is enabled, the event requires observing a fresh
    active/armed Single acquisition before accepting ``SAVE`` as completion. The
    bounded wait prevents a never-triggering scope from blocking the worker
    indefinitely. Artifact writing starts only after successful completion.
    """

    acquisition_active: bool | None = None
    trigger_state = ""
    observed_fresh = False
    if config.single_acquisition:
        wait = wait_for_fresh_single(
            scope,
            cancel,
            poll_interval_s=config.poll_interval_s,
            timeout_s=config.trigger_timeout_s,
        )
        acquisition_active = wait.acquisition_active
        trigger_state = wait.trigger_state
        observed_fresh = wait.observed_fresh_state
        if not wait.completed:
            return _wait_result(
                cancelled=wait.cancelled,
                timed_out=wait.timed_out,
                observed_fresh_state=wait.observed_fresh_state,
                acquisition_active=wait.acquisition_active,
                trigger_state=wait.trigger_state,
            )

    artifacts = capture_artifacts(
        scope,
        config.action,
        image_path=image_path,
        csv_path=csv_path,
    )
    return BurstEventResult(
        cancelled=False,
        timed_out=False,
        observed_fresh_state=observed_fresh,
        acquisition_active=acquisition_active,
        trigger_state=trigger_state,
        artifacts=artifacts,
    )


__all__ = [
    "MIN_BURST_DELAY_S",
    "BurstConfig",
    "BurstEventResult",
    "run_burst_event",
]
