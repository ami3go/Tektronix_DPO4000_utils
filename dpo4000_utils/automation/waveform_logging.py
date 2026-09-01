"""Framework-neutral A4 timed waveform capture helper."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import is_transport_error


@dataclass(frozen=True)
class TimedWaveformResult:
    """Result of one full-record CSV waveform capture."""

    csv_path: Path | None
    point_count: int = 0
    error: str = ""

    @property
    def success(self) -> bool:
        return self.csv_path is not None and not self.error


def save_full_record_csv(scope: Any, path: str | Path) -> TimedWaveformResult:
    """Save all enabled channels using the scope's current full record length.

    Transport failures propagate so the existing session recovery path can react.
    Non-transport file/serialization errors are returned as structured failures.
    """

    target = Path(path)
    point_count = 0
    try:
        point_count = int(scope.get_record_length())
        saved = Path(
            scope.save_all_channels_to_single_csv(
                target,
                point_count=point_count,
            )
        )
    except Exception as exc:  # noqa: BLE001 - distinguish transport from output failure.
        if is_transport_error(exc):
            raise
        return TimedWaveformResult(csv_path=None, point_count=point_count, error=str(exc))
    return TimedWaveformResult(csv_path=saved, point_count=point_count)


__all__ = ["TimedWaveformResult", "save_full_record_csv"]
