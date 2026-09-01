from __future__ import annotations

from array import array
from datetime import datetime, timezone

from dpo4000_utils.logger.csv_stream import WaveformCsvStreamWriter
from dpo4000_utils.logger.models import LoggerRecord, WaveformSnapshot


def _snapshot() -> WaveformSnapshot:
    return WaveformSnapshot(
        source="CH1",
        label="CH1",
        start_index=1,
        stop_index=2,
        acquired_utc=datetime.now(timezone.utc).isoformat(),
        typecode="h",
        sample_bytes=array("h", [10, 20]).tobytes(),
        sample_count=2,
        byte_order="little",
        preamble={
            "x_unit": "s",
            "x_increment": 1.0,
            "x_zero": 0.0,
            "point_offset": 0.0,
            "y_offset": 0.0,
            "y_multiplier": 0.1,
            "y_zero": 0.0,
        },
    )


def test_csv_stream_appends_multiple_complete_records(tmp_path) -> None:
    path = tmp_path / "run.csv"
    writer = WaveformCsvStreamWriter(path)
    writer.append(LoggerRecord(sequence=1, captured_utc="t1", waveforms=(_snapshot(),)))
    writer.append(LoggerRecord(sequence=2, captured_utc="t2", waveforms=(_snapshot(),)))
    writer.close()
    text = path.read_text(encoding="utf-8")
    assert text.count("record,") == 2
    assert "record,1,t1" in text
    assert "record,2,t2" in text
    assert writer.records_written == 2
