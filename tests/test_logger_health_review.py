from __future__ import annotations

from dpo4000_utils.logger.health import LoggerHealthAccumulator
from dpo4000_utils.logger.models import LoggerRecord, WaveformSnapshot


def test_l13_health_accumulator_does_not_retain_waveform_payload_objects() -> None:
    health = LoggerHealthAccumulator()
    waveform = WaveformSnapshot(
        source="CH1",
        label="CH1",
        start_index=1,
        stop_index=2,
        acquired_utc="2026-09-03T19:00:00+00:00",
        typecode="h",
        sample_bytes=b"\x00\x01\x00\x02",
        sample_count=2,
        byte_order="big",
        preamble={
            "x_zero": 0.0,
            "x_increment": 1.0,
            "point_offset": 0.0,
            "y_offset": 0.0,
            "y_multiplier": 1.0,
            "y_zero": 0.0,
        },
    )
    record = LoggerRecord(
        sequence=7,
        captured_utc="2026-09-03T19:00:01+00:00",
        waveforms=(waveform,),
    )
    health.note_capture(record, 0.1)
    snapshot = health.snapshot()
    assert snapshot.waveform_points == 2
    assert snapshot.waveform_payload_bytes == 4
    assert not hasattr(snapshot, "waveforms")
    assert not hasattr(snapshot, "sample_bytes")
