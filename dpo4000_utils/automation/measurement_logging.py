"""Framework-neutral A5 measurement logger."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..control import MEASUREMENT_SLOTS
from ..errors import is_transport_error


@dataclass(frozen=True)
class MeasurementLogResult:
    """Result of one appended MEAS1..MEAS8 time-series row."""

    csv_path: Path | None
    values: dict[int, str] = field(default_factory=dict)
    slot_errors: dict[int, str] = field(default_factory=dict)
    error: str = ""

    @property
    def success(self) -> bool:
        return self.csv_path is not None and not self.error


def normalize_measurement_slots(slots: Iterable[int]) -> tuple[int, ...]:
    """Validate, de-duplicate, and preserve selected measurement-slot order."""

    normalized: list[int] = []
    for raw in slots:
        if isinstance(raw, bool):
            raise ValueError("Measurement logger slots must be integers from 1 to 8.")
        slot = int(raw)
        if slot not in MEASUREMENT_SLOTS:
            raise ValueError("Measurement logger slots must be between MEAS1 and MEAS8.")
        if slot not in normalized:
            normalized.append(slot)
    if not normalized:
        raise ValueError("Select at least one measurement slot to log.")
    return tuple(normalized)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def append_measurement_row(
    scope: Any,
    path: str | Path,
    slots: Iterable[int],
    *,
    run_started_utc: datetime,
    now_utc: datetime | None = None,
) -> MeasurementLogResult:
    """Read selected measurement slots and append one fixed-column CSV row.

    A non-transport read failure for one slot is represented by an empty CSV field
    and returned in ``slot_errors``. Transport failures propagate. Filesystem or
    schema failures are returned as structured output errors.
    """

    selected = normalize_measurement_slots(slots)
    started = _ensure_utc(run_started_utc)
    now = _ensure_utc(now_utc or datetime.now(timezone.utc))
    target = Path(path)

    values: dict[int, str] = {}
    slot_errors: dict[int, str] = {}
    for slot in selected:
        try:
            values[slot] = str(scope.read_measurement_value(slot)).strip()
        except Exception as exc:  # noqa: BLE001 - classify transport vs per-slot read failure.
            if is_transport_error(exc):
                raise
            values[slot] = ""
            slot_errors[slot] = str(exc)

    header = ["utc_timestamp", "local_timestamp", "elapsed_s"] + [
        f"MEAS{slot}" for slot in selected
    ]
    row = [
        now.isoformat(),
        now.astimezone().isoformat(),
        f"{max(0.0, (now - started).total_seconds()):.6f}",
    ] + [values[slot] for slot in selected]

    try:
        write_header = not target.exists() or target.stat().st_size == 0
        if not write_header:
            with target.open("r", encoding="utf-8", newline="") as handle:
                existing_header = next(csv.reader(handle), [])
            if existing_header != header:
                return MeasurementLogResult(
                    csv_path=None,
                    values=values,
                    slot_errors=slot_errors,
                    error="Measurement CSV header does not match the active slot configuration.",
                )
        with target.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            if write_header:
                writer.writerow(header)
            writer.writerow(row)
            handle.flush()
    except Exception as exc:  # noqa: BLE001 - output failure is not a scope transport failure.
        return MeasurementLogResult(
            csv_path=None,
            values=values,
            slot_errors=slot_errors,
            error=str(exc),
        )

    return MeasurementLogResult(
        csv_path=target,
        values=values,
        slot_errors=slot_errors,
    )


__all__ = [
    "MeasurementLogResult",
    "append_measurement_row",
    "normalize_measurement_slots",
]
