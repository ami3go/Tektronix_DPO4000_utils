"""Append-only CSV segment writers for sustained Logger output."""

from __future__ import annotations

import csv
import os
from pathlib import Path

from .models import LoggerRecord, WaveformSnapshot


def _samples(snapshot: WaveformSnapshot):
    return snapshot.samples()


class WaveformCsvStreamWriter:
    """Append complete waveform records to one CSV segment and flush per record."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("x", encoding="utf-8", newline="")
        self._writer = csv.writer(self._handle)
        self.records_written = 0
        self.bytes_written = 0
        self._closed = False
        self._writer.writerow(["DPO4000_LOGGER_CSV", "schema", 1])
        self._flush()

    def _flush(self) -> None:
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self.bytes_written = self.path.stat().st_size

    def append(self, record: LoggerRecord) -> None:
        if self._closed:
            raise RuntimeError("CSV stream writer is closed.")
        if not record.waveforms:
            raise ValueError("Waveform CSV segment requires waveform data.")
        first = record.waveforms[0]
        raw_by_source = {item.source: _samples(item) for item in record.waveforms}
        for waveform in record.waveforms[1:]:
            if waveform.sample_count != first.sample_count:
                raise ValueError("Logger waveform sources are not sample-count aligned.")
            for field in ("x_increment", "x_zero", "point_offset", "x_unit"):
                if waveform.preamble[field] != first.preamble[field]:
                    raise ValueError(f"Logger waveform X-axis mismatch: {field}.")
        self._writer.writerow([])
        self._writer.writerow(["record", record.sequence, record.captured_utc])
        self._writer.writerow([
            "sample_index",
            f"time_{first.preamble['x_unit'] or 's'}",
            *[waveform.source for waveform in record.waveforms],
        ])
        for index in range(first.sample_count):
            values: list[float] = []
            for waveform in record.waveforms:
                raw = raw_by_source[waveform.source][index]
                values.append(
                    (raw - float(waveform.preamble["y_offset"]))
                    * float(waveform.preamble["y_multiplier"])
                    + float(waveform.preamble["y_zero"])
                )
            self._writer.writerow([index, first.time_at(index), *values])
        self.records_written += 1
        self._flush()

    def close(self) -> None:
        if self._closed:
            return
        self._flush()
        self._handle.close()
        self._closed = True

    def __enter__(self) -> "WaveformCsvStreamWriter":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


__all__ = ["WaveformCsvStreamWriter"]
