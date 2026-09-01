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
from .triggered import TriggerImageConfig, trigger_acquisition_complete


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
) -> TriggerBundleResult:
    """Arm Single, wait for completion, then save image and CSV before any re-arm.

    All scope-facing calls use the public driver API. PNG and CSV are therefore
    read while the same completed Single acquisition remains stopped. The caller
    decides whether to re-arm only after this function returns successfully.

    Non-transport artifact failures are returned as structured partial results so
    a disk/serialization problem does not masquerade as a lost VISA connection.
    Transport failures still propagate to the existing session invalidation path.
    """

    poll = TriggerImageConfig(poll_interval_s=poll_interval_s, rearm=False).poll_interval_s
    requested_image = Path(image_path)
    requested_csv = Path(csv_path)

    scope.single_acquisition()
    last_active = True
    last_trigger_state = "ARMED"

    while True:
        if cancel.is_set():
            scope.stop_acquisition()
            return TriggerBundleResult(
                completed=False,
                cancelled=True,
                acquisition_active=last_active,
                trigger_state=last_trigger_state,
            )

        last_active = bool(scope.get_acquisition_state())
        last_trigger_state = str(scope.get_trigger_state())
        if trigger_acquisition_complete(
            acquisition_active=last_active,
            trigger_state=last_trigger_state,
        ):
            try:
                saved_image = Path(scope.save_image_path(requested_image))
            except Exception as exc:  # noqa: BLE001 - classify transport vs artifact failure.
                return _artifact_failure_result(
                    exc=exc,
                    acquisition_active=last_active,
                    trigger_state=last_trigger_state,
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
                    acquisition_active=last_active,
                    trigger_state=last_trigger_state,
                    image_path=saved_image,
                    csv_path=None,
                    point_count=point_count,
                    operation="CSV save failed",
                )

            return TriggerBundleResult(
                completed=True,
                cancelled=False,
                acquisition_active=last_active,
                trigger_state=last_trigger_state,
                image_path=saved_image,
                csv_path=saved_csv,
                point_count=point_count,
            )

        if cancel.wait(poll):
            scope.stop_acquisition()
            return TriggerBundleResult(
                completed=False,
                cancelled=True,
                acquisition_active=last_active,
                trigger_state=last_trigger_state,
            )


__all__ = [
    "CancelSignal",
    "TriggerBundleResult",
    "acquire_trigger_bundle",
    "collision_safe_bundle_paths",
]
