from __future__ import annotations

from pathlib import Path

import pytest

from dpo4000_utils.logger.buffering import BufferPolicy, BufferSnapshot
from dpo4000_utils.logger.health import LoggerHealthAccumulator, compute_logger_health
from dpo4000_utils.logger.models import LoggerRecord, WaveformSnapshot


def _waveform(source: str = "CH1", points: int = 4) -> WaveformSnapshot:
    return WaveformSnapshot(
        source=source,
        label=source,
        start_index=1,
        stop_index=points,
        acquired_utc="2026-09-03T19:00:00+00:00",
        typecode="h",
        sample_bytes=b"\x00\x01" * points,
        sample_count=points,
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


def test_health_accumulator_tracks_scope_side_payload_without_retaining_records() -> None:
    health = LoggerHealthAccumulator()
    health.note_capture(
        LoggerRecord(
            sequence=1,
            captured_utc="2026-09-03T19:00:01+00:00",
            waveforms=(_waveform("CH1", 4), _waveform("MATH", 3)),
            measurements={1: 1.0, 2: None},
            bus_events={1: ({"event": "a"}, {"event": "b"})},
            metadata={"partial": True},
        ),
        0.25,
    )
    snapshot = health.snapshot()
    assert snapshot.captured_records == 1
    assert snapshot.waveform_points == 7
    assert snapshot.waveform_payload_bytes == 14
    assert snapshot.measurement_rows == 1
    assert snapshot.measurement_values == 1
    assert snapshot.bus_events == 2
    assert snapshot.last_record_sequence == 1
    assert snapshot.last_record_partial is True
    assert snapshot.last_scope_operation_s == pytest.approx(0.25)


def test_health_metrics_use_logger_rates_not_scope_sample_rate() -> None:
    health = LoggerHealthAccumulator()
    health.note_capture(
        LoggerRecord(
            sequence=1,
            captured_utc="2026-09-03T19:00:01+00:00",
            waveforms=(_waveform(points=100),),
        ),
        0.4,
    )
    health.note_capture(
        LoggerRecord(
            sequence=2,
            captured_utc="2026-09-03T19:00:02+00:00",
            waveforms=(_waveform(points=100),),
        ),
        0.5,
    )
    writer = BufferSnapshot(
        queued_records=2,
        queued_bytes=25,
        peak_records=3,
        peak_bytes=50,
        written_records=2,
        bytes_written=4_000_000,
        total_write_s=2.0,
    )
    policy = BufferPolicy(max_records=4, max_bytes=100, stop_after_overflows=5)
    metrics = compute_logger_health(
        health.snapshot(),
        writer,
        elapsed_s=10.0,
        buffer_policy=policy,
    )
    assert metrics.capture_records_per_s == pytest.approx(0.2)
    assert metrics.effective_records_per_s == pytest.approx(0.2)
    assert metrics.waveform_points_per_s == pytest.approx(20.0)
    assert metrics.scope_payload_bytes_per_s == pytest.approx(40.0)
    assert metrics.disk_bytes_per_s == pytest.approx(400_000.0)
    assert metrics.writer_duty_fraction == pytest.approx(0.2)
    assert metrics.queue_record_fraction == pytest.approx(0.5)
    assert metrics.queue_byte_fraction == pytest.approx(0.25)


def test_health_metrics_are_safe_at_zero_elapsed() -> None:
    metrics = compute_logger_health(
        LoggerHealthAccumulator().snapshot(),
        BufferSnapshot(),
        elapsed_s=0.0,
        buffer_policy=BufferPolicy(),
    )
    assert metrics.effective_records_per_s == 0.0
    assert metrics.disk_bytes_per_s == 0.0


def test_health_rejects_invalid_durations() -> None:
    health = LoggerHealthAccumulator()
    with pytest.raises(ValueError):
        health.note_capture(LoggerRecord(sequence=1, captured_utc="x"), float("nan"))
    with pytest.raises(ValueError):
        compute_logger_health(health.snapshot(), BufferSnapshot(), elapsed_s=-1.0)


def test_l13_gui_has_no_direct_visa_or_scpi_path() -> None:
    source = (
        Path(__file__).parents[1]
        / "dpo4000_utils"
        / "gui_qt"
        / "logger_health_window.py"
    ).read_text(encoding="utf-8").lower()
    assert "pyvisa" not in source
    assert "resource_manager" not in source
    assert "curve?" not in source
    assert "acquire:" not in source
