from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event

from dpo4000_utils.logger.buffering import BufferPolicy, LoggerWriterWorker
from dpo4000_utils.logger.models import LoggerRecord


def _record(sequence: int) -> LoggerRecord:
    return LoggerRecord(sequence=sequence, captured_utc="2026-09-06T00:00:00+00:00")


@dataclass
class _FastOutput:
    records: list[int] = field(default_factory=list)
    closed: bool = False
    bytes_written: int = 0
    segment_index: int = 0
    rotation_count: int = 0
    current_segment_bytes: int = 0
    current_paths: tuple = ()

    def append(self, record: LoggerRecord) -> None:
        self.records.append(record.sequence)
        self.bytes_written += 100
        self.current_segment_bytes += 100

    def close(self) -> None:
        self.closed = True


@dataclass
class _BlockingOutput(_FastOutput):
    entered: Event = field(default_factory=Event)
    release: Event = field(default_factory=Event)

    def append(self, record: LoggerRecord) -> None:
        self.entered.set()
        if not self.release.wait(5.0):
            raise TimeoutError("stress output was not released")
        super().append(record)


def test_logger_writer_drains_five_thousand_records_fifo() -> None:
    output = _FastOutput()
    total = 5_000
    writer = LoggerWriterWorker(
        lambda: output,
        BufferPolicy(
            max_records=total + 10,
            max_bytes=128 * 1024 * 1024,
            stop_after_overflows=100,
        ),
    )
    writer.start()

    for sequence in range(total):
        assert writer.try_enqueue(_record(sequence))

    writer.request_stop(drain=True)
    assert writer.wait(10.0)
    snapshot = writer.snapshot()

    assert output.closed
    assert output.records == list(range(total))
    assert snapshot.enqueued_records == total
    assert snapshot.written_records == total
    assert snapshot.dropped_records == 0
    assert snapshot.write_failed_records == 0
    assert snapshot.overflow_events == 0
    assert snapshot.queued_records == 0
    assert snapshot.inflight_records == 0
    assert snapshot.error == ""
    assert snapshot.stopped


def test_logger_queue_pressure_stays_bounded_and_accounts_every_drop() -> None:
    output = _BlockingOutput()
    policy = BufferPolicy(
        max_records=32,
        max_bytes=8 * 1024 * 1024,
        stop_after_overflows=1_000,
    )
    writer = LoggerWriterWorker(lambda: output, policy)
    writer.start()

    assert writer.try_enqueue(_record(0))
    assert output.entered.wait(2.0)

    accepted = 1
    rejected = 0
    for sequence in range(1, 500):
        if writer.try_enqueue(_record(sequence)):
            accepted += 1
        else:
            rejected += 1

    blocked_snapshot = writer.snapshot()
    assert blocked_snapshot.inflight_records == 1
    assert blocked_snapshot.queued_records + blocked_snapshot.inflight_records <= policy.max_records
    assert blocked_snapshot.peak_records <= policy.max_records
    assert rejected > 0
    assert blocked_snapshot.dropped_records == rejected
    assert blocked_snapshot.overflow_events == rejected

    writer.request_stop(drain=True)
    output.release.set()
    assert writer.wait(10.0)
    final_snapshot = writer.snapshot()

    assert output.closed
    assert final_snapshot.written_records == accepted
    assert final_snapshot.dropped_records == rejected
    assert final_snapshot.enqueued_records == accepted
    assert final_snapshot.queued_records == 0
    assert final_snapshot.inflight_records == 0
    assert final_snapshot.write_failed_records == 0
    assert final_snapshot.error == ""
    assert final_snapshot.stopped


def test_logger_repeated_start_drain_shutdown_cycles_close_outputs() -> None:
    outputs: list[_FastOutput] = []

    for cycle in range(30):
        output = _FastOutput()
        outputs.append(output)
        writer = LoggerWriterWorker(
            lambda output=output: output,
            BufferPolicy(max_records=64, max_bytes=4 * 1024 * 1024),
        )
        writer.start()
        for offset in range(20):
            assert writer.try_enqueue(_record(cycle * 20 + offset))
        writer.request_stop(drain=True)
        assert writer.wait(3.0)
        snapshot = writer.snapshot()
        assert snapshot.written_records == 20
        assert snapshot.dropped_records == 0
        assert snapshot.error == ""
        assert snapshot.stopped

    assert all(output.closed for output in outputs)
    assert sum(len(output.records) for output in outputs) == 600
