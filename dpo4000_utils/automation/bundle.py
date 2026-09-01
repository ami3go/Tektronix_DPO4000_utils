"""Framework-neutral A3 trigger bundle orchestration.

The helper in this module deliberately knows nothing about Qt, SCPI strings, or
PyVISA. It drives only the public DPO4000 driver API so the exact arm/wait/save
order can be unit tested and reused by future headless automation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

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
            saved_image = Path(scope.save_image_path(requested_image))
            point_count = int(scope.get_record_length())
            saved_csv = Path(
                scope.save_all_channels_to_single_csv(
                    requested_csv,
                    point_count=point_count,
                )
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


__all__ = ["CancelSignal", "TriggerBundleResult", "acquire_trigger_bundle"]
