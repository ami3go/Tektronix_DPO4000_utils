"""Tagged-row CSV writer for synchronized mixed Logger records."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from .models import LoggerRecord


class MixedCsvStreamWriter:
    """Store waveform, measurement and BUS content under one acquisition sequence."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("x", encoding="utf-8", newline="")
        self._writer = csv.writer(self._handle)
        self._closed = False
        self.records_written = 0
        self.bytes_written = 0
        self._writer.writerow([
            "row_type", "record_sequence", "captured_utc", "source", "index_or_time",
            "value", "status", "details_json",
        ])
        self._flush()

    def _flush(self) -> None:
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self.bytes_written = self.path.stat().st_size

    def append(self, record: LoggerRecord) -> None:
        if self._closed:
            raise RuntimeError("Mixed CSV writer is closed.")
        self._writer.writerow([
            "RECORD", record.sequence, record.captured_utc, "", "", "",
            "partial" if record.metadata.get("partial") else "complete",
            json.dumps(dict(record.metadata), sort_keys=True, default=str),
        ])
        for slot, value in sorted(record.measurements.items()):
            error = record.measurement_errors.get(slot, "")
            self._writer.writerow([
                "MEAS", record.sequence, record.captured_utc, f"MEAS{slot}", "",
                "" if value is None else value, error,
                "{}",
            ])
        for bus, events in sorted(record.bus_events.items()):
            for event in events:
                values = dict(event)
                self._writer.writerow([
                    "BUS", record.sequence, record.captured_utc, f"BUS{bus}",
                    values.get("timestamp_s", ""), values.get("data", ""),
                    values.get("event_type", ""), json.dumps(values, sort_keys=True, default=str),
                ])
        for waveform in record.waveforms:
            samples = waveform.samples()
            for index, raw in enumerate(samples):
                engineering = (
                    (raw - float(waveform.preamble["y_offset"]))
                    * float(waveform.preamble["y_multiplier"])
                    + float(waveform.preamble["y_zero"])
                )
                self._writer.writerow([
                    "WAVE", record.sequence, record.captured_utc, waveform.source,
                    waveform.time_at(index), engineering, "", str(index),
                ])
        self.records_written += 1
        self._flush()

    def close(self) -> None:
        if self._closed:
            return
        self._flush()
        self._handle.close()
        self._closed = True


__all__ = ["MixedCsvStreamWriter"]
