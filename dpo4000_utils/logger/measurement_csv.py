"""Fixed-schema append-only CSV writer for Logger measurement mode."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from .models import LoggerRecord
from .sync import CsvSyncController, CsvSyncPolicy


def _captured_local_timestamp(captured_utc: str) -> str:
    value = datetime.fromisoformat(str(captured_utc).replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Logger captured_utc must include timezone information.")
    return value.astimezone().isoformat()


class MeasurementCsvStreamWriter:
    def __init__(
        self,
        path: str | Path,
        slots: tuple[int, ...],
        *,
        sync_policy: CsvSyncPolicy | None = None,
    ) -> None:
        if not slots:
            raise ValueError("Measurement CSV writer requires at least one MEAS slot.")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.slots = tuple(int(slot) for slot in slots)
        self._handle = self.path.open("x", encoding="utf-8", newline="")
        self._writer = csv.writer(self._handle)
        self._sync = CsvSyncController(self._handle, self.path, sync_policy)
        self._first_capture_monotonic: float | None = None
        self.records_written = 0
        self.bytes_written = 0
        self._closed = False
        self._writer.writerow([
            "utc_timestamp",
            "local_timestamp",
            "elapsed_s",
            "record_sequence",
            *[f"MEAS{slot}" for slot in self.slots],
            "status_json",
        ])
        self.bytes_written = self._sync.force()

    def _elapsed_from_capture(self, record: LoggerRecord) -> float:
        captured = float(record.captured_monotonic)
        if captured <= 0:
            return 0.0
        if self._first_capture_monotonic is None:
            self._first_capture_monotonic = captured
        return max(0.0, captured - self._first_capture_monotonic)

    def append(self, record: LoggerRecord) -> None:
        if self._closed:
            raise RuntimeError("Measurement CSV writer is closed.")
        values = [record.measurements.get(slot) for slot in self.slots]
        errors = {
            f"MEAS{slot}": record.measurement_errors[slot]
            for slot in self.slots
            if slot in record.measurement_errors
        }
        self._writer.writerow([
            record.captured_utc,
            _captured_local_timestamp(record.captured_utc),
            f"{self._elapsed_from_capture(record):.9f}",
            record.sequence,
            *["" if value is None else value for value in values],
            json.dumps(errors, sort_keys=True, separators=(",", ":")),
        ])
        self.records_written += 1
        self.bytes_written = self._sync.after_record()

    def close(self) -> None:
        if self._closed:
            return
        try:
            self.bytes_written = self._sync.close()
        finally:
            self._handle.close()
            self._closed = True


__all__ = ["MeasurementCsvStreamWriter"]
