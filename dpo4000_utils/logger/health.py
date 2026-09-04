"""Framework-neutral Logger runtime health accounting.

The rates in this module describe Logger-observed transfer and persistence
throughput. They are deliberately not oscilloscope acquisition sample-rate
measurements.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .buffering import BufferPolicy, BufferSnapshot
from .models import LoggerRecord


@dataclass(frozen=True)
class LoggerCaptureHealth:
    captured_records: int = 0
    waveform_points: int = 0
    waveform_payload_bytes: int = 0
    measurement_rows: int = 0
    measurement_values: int = 0
    bus_events: int = 0
    last_record_sequence: int | None = None
    last_record_utc: str = ""
    last_record_partial: bool = False
    last_scope_operation_s: float = 0.0


@dataclass(frozen=True)
class LoggerHealthMetrics:
    elapsed_s: float = 0.0
    capture_records_per_s: float = 0.0
    effective_records_per_s: float = 0.0
    waveform_points_per_s: float = 0.0
    scope_payload_bytes_per_s: float = 0.0
    disk_bytes_per_s: float = 0.0
    writer_duty_fraction: float = 0.0
    queue_record_fraction: float = 0.0
    queue_byte_fraction: float = 0.0


class LoggerHealthAccumulator:
    """Accumulate successful scope-side Logger records without retaining payloads."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._captured_records = 0
        self._waveform_points = 0
        self._waveform_payload_bytes = 0
        self._measurement_rows = 0
        self._measurement_values = 0
        self._bus_events = 0
        self._last_record_sequence: int | None = None
        self._last_record_utc = ""
        self._last_record_partial = False
        self._last_scope_operation_s = 0.0

    def note_capture(self, record: LoggerRecord, scope_operation_s: float) -> None:
        elapsed = float(scope_operation_s)
        if not math.isfinite(elapsed) or elapsed < 0.0:
            raise ValueError("Scope operation duration must be finite and non-negative.")
        self._captured_records += 1
        self._waveform_points += sum(int(waveform.sample_count) for waveform in record.waveforms)
        self._waveform_payload_bytes += sum(
            len(waveform.sample_bytes) for waveform in record.waveforms
        )
        if record.measurements:
            self._measurement_rows += 1
            self._measurement_values += sum(
                1 for value in record.measurements.values() if value is not None
            )
        self._bus_events += sum(len(events) for events in record.bus_events.values())
        self._last_record_sequence = int(record.sequence)
        self._last_record_utc = str(record.captured_utc)
        self._last_record_partial = bool(record.metadata.get("partial", False))
        self._last_scope_operation_s = elapsed

    def snapshot(self) -> LoggerCaptureHealth:
        return LoggerCaptureHealth(
            captured_records=self._captured_records,
            waveform_points=self._waveform_points,
            waveform_payload_bytes=self._waveform_payload_bytes,
            measurement_rows=self._measurement_rows,
            measurement_values=self._measurement_values,
            bus_events=self._bus_events,
            last_record_sequence=self._last_record_sequence,
            last_record_utc=self._last_record_utc,
            last_record_partial=self._last_record_partial,
            last_scope_operation_s=self._last_scope_operation_s,
        )


def compute_logger_health(
    capture: LoggerCaptureHealth,
    writer: BufferSnapshot,
    *,
    elapsed_s: float,
    buffer_policy: BufferPolicy | None = None,
) -> LoggerHealthMetrics:
    """Compute stable cumulative Logger rates and queue pressure."""
    elapsed = float(elapsed_s)
    if not math.isfinite(elapsed) or elapsed < 0.0:
        raise ValueError("Logger elapsed time must be finite and non-negative.")
    denominator = elapsed if elapsed > 0.0 else 0.0

    def rate(value: int | float) -> float:
        return float(value) / denominator if denominator else 0.0

    queue_record_fraction = 0.0
    queue_byte_fraction = 0.0
    if buffer_policy is not None:
        queue_record_fraction = min(
            1.0, max(0.0, writer.queued_records / float(buffer_policy.max_records))
        )
        queue_byte_fraction = min(
            1.0, max(0.0, writer.queued_bytes / float(buffer_policy.max_bytes))
        )

    writer_duty = 0.0
    if denominator:
        writer_duty = min(1.0, max(0.0, writer.total_write_s / denominator))

    return LoggerHealthMetrics(
        elapsed_s=elapsed,
        capture_records_per_s=rate(capture.captured_records),
        effective_records_per_s=rate(writer.written_records),
        waveform_points_per_s=rate(capture.waveform_points),
        scope_payload_bytes_per_s=rate(capture.waveform_payload_bytes),
        disk_bytes_per_s=rate(writer.bytes_written),
        writer_duty_fraction=writer_duty,
        queue_record_fraction=queue_record_fraction,
        queue_byte_fraction=queue_byte_fraction,
    )


__all__ = [
    "LoggerCaptureHealth",
    "LoggerHealthAccumulator",
    "LoggerHealthMetrics",
    "compute_logger_health",
]
