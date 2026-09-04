"""Fixed-schema append-only CSV writer for Logger measurement mode."""

from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from .models import LoggerRecord


class MeasurementCsvStreamWriter:
    def __init__(self, path: str | Path, slots: tuple[int, ...]) -> None:
        if not slots:
            raise ValueError("Measurement CSV writer requires at least one MEAS slot.")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.slots = tuple(int(slot) for slot in slots)
        self._handle = self.path.open("x", encoding="utf-8", newline="")
        self._writer = csv.writer(self._handle)
        self._started = time.monotonic()
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
        self._flush()

    def _flush(self) -> None:
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self.bytes_written = self.path.stat().st_size

    def append(self, record: LoggerRecord) -> None:
        if self._closed:
            raise RuntimeError("Measurement CSV writer is closed.")
        values = [record.measurements.get(slot) for slot in self.slots]
        errors = {
            f"MEAS{slot}": record.measurement_errors[slot]
            for slot in self.slots
            if slot in record.measurement_errors
        }
        now_local = datetime.now().astimezone().isoformat()
        elapsed = max(0.0, time.monotonic() - self._started)
        self._writer.writerow([
            record.captured_utc,
            now_local,
            f"{elapsed:.9f}",
            record.sequence,
            *["" if value is None else value for value in values],
            json.dumps(errors, sort_keys=True, separators=(",", ":")),
        ])
        self.records_written += 1
        self._flush()

    def close(self) -> None:
        if self._closed:
            return
        self._flush()
        self._handle.close()
        self._closed = True


__all__ = ["MeasurementCsvStreamWriter"]
