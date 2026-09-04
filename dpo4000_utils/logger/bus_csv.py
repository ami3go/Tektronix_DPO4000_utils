"""Normalized append-only CSV writer for decoded BUS Logger events."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import LoggerRecord
from .sync import CsvSyncController, CsvSyncPolicy

_COMMON = {"protocol", "timestamp_s", "event_type", "address", "data", "flags", "raw_text"}


class BusCsvStreamWriter:
    def __init__(self, path: str | Path, *, sync_policy: CsvSyncPolicy | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("x", encoding="utf-8", newline="")
        self._writer = csv.writer(self._handle)
        self._sync = CsvSyncController(self._handle, self.path, sync_policy)
        self._closed = False
        self.records_written = 0
        self.events_written = 0
        self.bytes_written = 0
        self._writer.writerow([
            "utc_timestamp",
            "acquisition_id",
            "bus",
            "protocol",
            "event_time_s",
            "event_type",
            "address",
            "data",
            "flags",
            "raw_text",
            "details_json",
        ])
        self.bytes_written = self._sync.force()

    def append(self, record: LoggerRecord) -> None:
        if self._closed:
            raise RuntimeError("BUS CSV writer is closed.")
        for bus, events in sorted(record.bus_events.items()):
            for event in events:
                values = dict(event)
                details = {
                    key: value
                    for key, value in values.items()
                    if key not in _COMMON and key != "bus"
                }
                self._writer.writerow([
                    record.captured_utc,
                    record.sequence,
                    bus,
                    values.get("protocol", ""),
                    values.get("timestamp_s", ""),
                    values.get("event_type", ""),
                    values.get("address", ""),
                    values.get("data", ""),
                    values.get("flags", ""),
                    values.get("raw_text", ""),
                    json.dumps(details, sort_keys=True, separators=(",", ":"), default=str),
                ])
                self.events_written += 1
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


__all__ = ["BusCsvStreamWriter"]
