"""Initial per-record Logger CSV persistence used by L1/L2."""

from __future__ import annotations

import csv
from pathlib import Path

from .models import LoggerRecord, WaveformSnapshot


def _raw_values(snapshot: WaveformSnapshot):
    return snapshot.samples()


def write_waveform_record_csv(path: str | Path, record: LoggerRecord) -> Path:
    """Write one aligned waveform acquisition record as a wide CSV file."""
    if not record.waveforms:
        raise ValueError("Logger record contains no waveform data.")
    first = record.waveforms[0]
    for waveform in record.waveforms[1:]:
        if waveform.sample_count != first.sample_count:
            raise ValueError("Logger waveform sources are not sample-count aligned.")
        for field in ("x_increment", "x_zero", "point_offset", "x_unit"):
            if waveform.preamble[field] != first.preamble[field]:
                raise ValueError(f"Logger waveform X-axis mismatch: {field}.")
    raw_by_source = {waveform.source: _raw_values(waveform) for waveform in record.waveforms}
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["record_sequence", record.sequence])
        writer.writerow(["captured_utc", record.captured_utc])
        writer.writerow(["sample_index", f"time_{first.preamble['x_unit'] or 's'}", *[w.source for w in record.waveforms]])
        for index in range(first.sample_count):
            values = []
            for waveform in record.waveforms:
                raw = raw_by_source[waveform.source][index]
                values.append(
                    (raw - float(waveform.preamble["y_offset"]))
                    * float(waveform.preamble["y_multiplier"])
                    + float(waveform.preamble["y_zero"])
                )
            writer.writerow([index, first.time_at(index), *values])
    return target


__all__ = ["write_waveform_record_csv"]
