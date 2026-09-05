"""Tagged-row CSV writer for synchronized mixed Logger records."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import LoggerRecord
from .sync import CsvSyncController, CsvSyncPolicy


class MixedCsvStreamWriter:
    """Store waveform, measurement and BUS content under one acquisition sequence.

    Each logical record is framed by ``RECORD_BEGIN`` and ``RECORD_END`` rows.
    ``RECORD_END`` is emitted only after all child rows were written, so a crash
    cannot make an incomplete record appear complete during recovery/inspection.
    """

    def __init__(self, path: str | Path, *, sync_policy: CsvSyncPolicy | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("x", encoding="utf-8", newline="")
        self._writer = csv.writer(self._handle)
        self._sync = CsvSyncController(self._handle, self.path, sync_policy)
        self._closed = False
        self.records_written = 0
        self.bytes_written = 0
        self._writer.writerow([
            "row_type", "record_sequence", "captured_utc", "source", "index_or_time",
            "value", "status", "details_json",
        ])
        self.bytes_written = self._sync.force()

    def append(self, record: LoggerRecord) -> None:
        if self._closed:
            raise RuntimeError("Mixed CSV writer is closed.")
        metadata_json = json.dumps(dict(record.metadata), sort_keys=True, default=str)
        final_status = "partial" if record.metadata.get("partial") else "complete"
        self._writer.writerow([
            "RECORD_BEGIN", record.sequence, record.captured_utc, "", "", "",
            "begin", metadata_json,
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
        self._writer.writerow([
            "RECORD_END", record.sequence, record.captured_utc, "", "", "",
            final_status, metadata_json,
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


__all__ = ["MixedCsvStreamWriter"]
