"""Framework-neutral A3 trigger bundle orchestration.

The helpers in this module deliberately know nothing about Qt, SCPI strings, or
PyVISA. They drive only the public DPO4000 driver API so the exact arm/wait/save
order can be unit tested and reused by future headless automation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..errors import is_transport_error
from .triggered import wait_for_fresh_single


class CancelSignal(Protocol):
    """Minimal cancellation interface used by worker-side trigger waits."""

    def is_set(self) -> bool: ...

    def wait(self, timeout: float) -> bool: ...


@dataclass(frozen=True)
class TriggerBundleResult:
    """Result from one A3 single-acquisition image + CSV capture."""

    completed: bool
    cancelled: bool
    acquisition_active: bool
    trigger_state: str
    timed_out: bool = False
    observed_fresh_state: bool = False
    image_path: Path | None = None
    csv_path: Path | None = None
    point_count: int = 0
    error: str = ""

    @property
    def artifacts_complete(self) -> bool:
        """Return True only when both requested artifacts were saved."""

        return self.image_path is not None and self.csv_path is not None and not self.error


def collision_safe_bundle_paths(
    image_path: str | Path,
    csv_path: str | Path,
    *,
    max_attempts: int = 9999,
) -> tuple[Path, Path]:
    """Allocate PNG/CSV paths with one shared collision suffix.

    If either requested path already exists, both names advance together so the
    two files retain an obvious one-to-one pairing.
    """

    image = Path(image_path)
    csv = Path(csv_path)
    if not image.exists() and not csv.exists():
        return image, csv

    for index in range(1, int(max_attempts) + 1):
        image_candidate = image.with_name(f"{image.stem}_{index:03d}{image.suffix}")
        csv_candidate = csv.with_name(f"{csv.stem}_{index:03d}{csv.suffix}")
        if not image_candidate.exists() and not csv_candidate.exists():
            return image_candidate, csv_candidate

    raise FileExistsError("Could not allocate collision-safe paths for the automation bundle.")


def _artifact_failure_result(
    *,
    exc: Exception,
    acquisition_active: bool,
    trigger_state: str,
    image_path: Path | None,
    csv_path: Path | None,
    point_count: int,
    operation: str,
) -> TriggerBundleResult:
    if is_transport_error(exc):
        raise exc
    return TriggerBundleResult(
        completed=True,
        cancelled=False,
        acquisition_active=acquisition_active,
        trigger_state=trigger_state,
        observed_fresh_state=True,
        image_path=image_path,
        csv_path=csv_path,
        point_count=point_count,
        error=f"{operation}: {exc}",
    )


def acquire_trigger_bundle(
    scope: Any,
    cancel: CancelSignal,
    *,
    poll_interval_s: float,
    image_path: str | Path,
    csv_path: str | Path,
    timeout_s: float = 30.0,
) -> TriggerBundleResult:
    """Arm a fresh Single, then save image and CSV before any re-arm.

    Completion is accepted only after the new acquisition was visibly active or
    armed. A stale pre-existing ``SAVE`` state cannot satisfy the wait. Timeout and
    cancellation both stop acquisition without writing evidence artifacts.

    Non-transport artifact failures are returned as structured partial results so
    a disk/serialization problem does not masquerade as a lost VISA connection.
    Transport failures still propagate to the existing session invalidation path.
    """

    requested_image = Path(image_path)
    requested_csv = Path(csv_path)
    wait = wait_for_fresh_single(
        scope,
        cancel,
        poll_interval_s=poll_interval_s,
        timeout_s=timeout_s,
    )
    if not wait.completed:
        error = ""
        if wait.timed_out:
            error = f"Single acquisition timed out after {timeout_s:g} s."
        return TriggerBundleResult(
            completed=False,
            cancelled=wait.cancelled,
            timed_out=wait.timed_out,
            observed_fresh_state=wait.observed_fresh_state,
            acquisition_active=wait.acquisition_active,
            trigger_state=wait.trigger_state,
            error=error,
        )

    try:
        saved_image = Path(scope.save_image_path(requested_image))
    except Exception as exc:  # noqa: BLE001 - classify transport vs artifact failure.
        return _artifact_failure_result(
            exc=exc,
            acquisition_active=wait.acquisition_active,
            trigger_state=wait.trigger_state,
            image_path=None,
            csv_path=None,
            point_count=0,
            operation="Image save failed",
        )

    point_count = 0
    try:
        point_count = int(scope.get_record_length())
        saved_csv = Path(
            scope.save_all_channels_to_single_csv(
                requested_csv,
                point_count=point_count,
            )
        )
    except Exception as exc:  # noqa: BLE001 - classify transport vs artifact failure.
        return _artifact_failure_result(
            exc=exc,
            acquisition_active=wait.acquisition_active,
            trigger_state=wait.trigger_state,
            image_path=saved_image,
            csv_path=None,
            point_count=point_count,
            operation="CSV save failed",
        )

    return TriggerBundleResult(
        completed=True,
        cancelled=False,
        acquisition_active=wait.acquisition_active,
        trigger_state=wait.trigger_state,
        observed_fresh_state=True,
        image_path=saved_image,
        csv_path=saved_csv,
        point_count=point_count,
    )


__all__ = [
    "CancelSignal",
    "TriggerBundleResult",
    "acquire_trigger_bundle",
    "collision_safe_bundle_paths",
]
