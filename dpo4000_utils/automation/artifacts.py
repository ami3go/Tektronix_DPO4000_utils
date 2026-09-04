"""Shared public-driver artifact capture helpers for Automation modes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ..errors import is_transport_error


class ArtifactAction(str, Enum):
    """Artifacts saved by an Automation event."""

    IMAGE = "Image"
    CSV = "CSV"
    IMAGE_CSV = "Image + CSV"


@dataclass(frozen=True)
class ArtifactCaptureResult:
    """Result of one image/CSV artifact save operation."""

    action: ArtifactAction
    image_path: Path | None = None
    csv_path: Path | None = None
    point_count: int = 0
    error: str = ""

    @property
    def success(self) -> bool:
        if self.error:
            return False
        if self.action is ArtifactAction.IMAGE:
            return self.image_path is not None
        if self.action is ArtifactAction.CSV:
            return self.csv_path is not None
        return self.image_path is not None and self.csv_path is not None


def normalize_artifact_action(action: ArtifactAction | str) -> ArtifactAction:
    """Normalize user/profile artifact action text."""

    if isinstance(action, ArtifactAction):
        return action
    text = str(action).strip().lower()
    aliases = {
        "image": ArtifactAction.IMAGE,
        "png": ArtifactAction.IMAGE,
        "csv": ArtifactAction.CSV,
        "image + csv": ArtifactAction.IMAGE_CSV,
        "image+csv": ArtifactAction.IMAGE_CSV,
        "png + csv": ArtifactAction.IMAGE_CSV,
        "png+csv": ArtifactAction.IMAGE_CSV,
    }
    try:
        return aliases[text]
    except KeyError as exc:
        raise ValueError(f"Unsupported automation artifact action: {action!r}.") from exc


def _error_with_partial_artifacts(
    exc: Exception,
    *,
    image_path: Path | None,
    csv_path: Path | None,
) -> str:
    detail = str(exc).strip() or exc.__class__.__name__
    partials: list[str] = []
    if image_path is not None:
        partials.append(str(image_path))
    if csv_path is not None:
        partials.append(str(csv_path))
    if partials:
        detail = f"{detail}; partial artifacts: {', '.join(partials)}"
    return detail


def capture_artifacts(
    scope: Any,
    action: ArtifactAction | str,
    *,
    image_path: str | Path | None = None,
    csv_path: str | Path | None = None,
) -> ArtifactCaptureResult:
    """Save selected artifacts through public DPO4000 driver APIs only.

    Transport failures propagate so the existing session invalidation/reconnect
    path can classify them. Protocol/filesystem failures are returned as a
    structured partial result so a successfully written first artifact is not
    mislabeled as a complete event.
    """

    selected = normalize_artifact_action(action)
    requested_image = Path(image_path) if image_path is not None else None
    requested_csv = Path(csv_path) if csv_path is not None else None
    if selected in {ArtifactAction.IMAGE, ArtifactAction.IMAGE_CSV} and requested_image is None:
        raise ValueError("Image capture requires an image output path.")
    if selected in {ArtifactAction.CSV, ArtifactAction.IMAGE_CSV} and requested_csv is None:
        raise ValueError("CSV capture requires a CSV output path.")

    saved_image: Path | None = None
    saved_csv: Path | None = None
    point_count = 0
    try:
        if selected in {ArtifactAction.IMAGE, ArtifactAction.IMAGE_CSV}:
            assert requested_image is not None
            saved_image = Path(scope.save_image_path(requested_image))
        if selected in {ArtifactAction.CSV, ArtifactAction.IMAGE_CSV}:
            assert requested_csv is not None
            point_count = int(scope.get_record_length())
            saved_csv = Path(
                scope.save_all_channels_to_single_csv(
                    requested_csv,
                    point_count=point_count,
                )
            )
    except Exception as exc:  # noqa: BLE001 - preserve transport classification.
        if is_transport_error(exc):
            raise
        return ArtifactCaptureResult(
            action=selected,
            image_path=saved_image,
            csv_path=saved_csv,
            point_count=point_count,
            error=_error_with_partial_artifacts(
                exc,
                image_path=saved_image,
                csv_path=saved_csv,
            ),
        )

    return ArtifactCaptureResult(
        action=selected,
        image_path=saved_image,
        csv_path=saved_csv,
        point_count=point_count,
    )


__all__ = [
    "ArtifactAction",
    "ArtifactCaptureResult",
    "capture_artifacts",
    "normalize_artifact_action",
]
