from __future__ import annotations

import time
from dataclasses import dataclass, field

import pytest

from dpo4000_utils.logger.buffering import BoundedRecordBuffer, BufferPolicy, LoggerWriterWorker
from dpo4000_utils.logger.models import LoggerRecord
from dpo4000_utils.regression import linear_slope, summarize_timings


def _record(sequence: int) -> LoggerRecord:
    return LoggerRecord(sequence=sequence, captured_utc="2026-09-14T00:00:00+00:00")


@dataclass
class _CountingOutput:
    records: int = 0
    bytes_written: int = 0
    segment_index: int = 0
    rotation_count: int = 0
    current_segment_bytes: int = 0
    current_paths: tuple = ()
    closed: bool = False
    sequences: list[int] = field(default_factory=list)

    def append(self, record: LoggerRecord) -> None:
        self.records += 1
        self.sequences.append(record.sequence)
        self.bytes_written += 64
        self.current_segment_bytes += 64

    def close(self) -> None:
        self.closed = True


def _simulate_load(load_fraction: float, *, cycles: int = 2_000) -> tuple[list[int], BoundedRecordBuffer]:
    """Deterministic producer/consumer model: consumer capacity is one record/cycle."""

    buffer = BoundedRecordBuffer(
        BufferPolicy(max_records=64, max_bytes=8 * 1024 * 1024, stop_after_overflows=10_000)
    )
    depths: list[int] = []
    production_credit = 0.0
    sequence = 0

    for _ in range(cycles):
        production_credit += load_fraction
        while production_credit >= 1.0:
            buffer.try_put(_record(sequence))
            sequence += 1
            production_credit -= 1.0

        item = buffer.take_left()
        if item is not None:
            buffer.commit_inflight()
        depths.append(buffer.resident_records)

    return depths, buffer


@pytest.mark.parametrize("load_fraction", (0.25, 0.50, 0.80, 1.00))
def test_logger_queue_has_no_persistent_positive_slope_at_sustainable_load(load_fraction: float) -> None:
    depths, buffer = _simulate_load(load_fraction)
    tail = depths[len(depths) // 2 :]

    assert max(depths) <= buffer.policy.max_records
    assert buffer.dropped_records == 0
    assert linear_slope(tail) <= 1e-9


def test_logger_queue_is_bounded_and_accounts_overload_at_120_percent() -> None:
    depths, buffer = _simulate_load(1.20, cycles=5_000)

    assert max(depths) <= buffer.policy.max_records
    assert buffer.peak_records <= buffer.policy.max_records
    assert buffer.dropped_records > 0
    assert buffer.overflow_events == buffer.dropped_records


def test_logger_writer_short_performance_smoke() -> None:
    """Shared-CI smoke budget; authoritative p95/p99 belongs on the controlled R0-T runner."""

    total = 2_000
    output = _CountingOutput()
    writer = LoggerWriterWorker(
        lambda: output,
        BufferPolicy(
            max_records=total + 8,
            max_bytes=64 * 1024 * 1024,
            stop_after_overflows=100,
        ),
    )
    writer.start()

    enqueue_durations: list[float] = []
    started = time.perf_counter()
    for sequence in range(total):
        before = time.perf_counter()
        assert writer.try_enqueue(_record(sequence))
        enqueue_durations.append(time.perf_counter() - before)

    writer.request_stop(drain=True)
    assert writer.wait(10.0)
    elapsed = time.perf_counter() - started
    snapshot = writer.snapshot()
    enqueue = summarize_timings(enqueue_durations)
    throughput = total / max(elapsed, 1e-9)

    assert output.closed
    assert output.sequences == list(range(total))
    assert snapshot.written_records == total
    assert snapshot.dropped_records == 0
    assert snapshot.error == ""
    assert throughput >= 100.0
    assert enqueue.p99 < 0.100
    assert elapsed < 10.0
