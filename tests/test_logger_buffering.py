from __future__ import annotations

from dataclasses import dataclass

from dpo4000_utils.logger.buffering import (
    BoundedRecordBuffer,
    BufferPolicy,
    LoggerWriterWorker,
)
from dpo4000_utils.logger.models import LoggerRecord


def _record(sequence: int) -> LoggerRecord:
    return LoggerRecord(sequence=sequence, captured_utc="2026-09-03T00:00:00+00:00")


def test_bounded_buffer_never_exceeds_record_limit() -> None:
    buffer = BoundedRecordBuffer(BufferPolicy(max_records=2, max_bytes=10_000))
    assert buffer.try_put(_record(1))
    assert buffer.try_put(_record(2))
    assert not buffer.try_put(_record(3))
    assert buffer.queued_records == 2
    assert buffer.dropped_records == 1
    assert buffer.overflow_events == 1


def test_bounded_buffer_enforces_estimated_memory_limit() -> None:
    buffer = BoundedRecordBuffer(BufferPolicy(max_records=10, max_bytes=1500))
    assert buffer.try_put(_record(1))
    assert not buffer.try_put(_record(2))
    assert buffer.queued_records == 1


def test_inflight_record_remains_charged_until_commit() -> None:
    buffer = BoundedRecordBuffer(BufferPolicy(max_records=1, max_bytes=10_000))
    assert buffer.try_put(_record(1))
    record = buffer.take_left()
    assert record is not None
    assert buffer.queued_records == 0
    assert buffer.inflight_records == 1
    assert buffer.resident_records == 1
    assert not buffer.try_put(_record(2))
    buffer.commit_inflight()
    assert buffer.resident_records == 0
    assert buffer.try_put(_record(2))


@dataclass
class _FakeOutput:
    records: list[int]
    closed: bool = False
    bytes_written: int = 0
    segment_index: int = 0
    rotation_count: int = 0
    current_segment_bytes: int = 0
    current_paths: tuple = ()
    fail_append: bool = False

    def append(self, record: LoggerRecord) -> None:
        if self.fail_append:
            raise OSError("disk write failed")
        self.records.append(record.sequence)
        self.bytes_written += 100
        self.current_segment_bytes += 100

    def close(self) -> None:
        self.closed = True


def test_writer_drains_fifo_and_owns_close() -> None:
    output = _FakeOutput([])
    writer = LoggerWriterWorker(
        lambda: output,
        BufferPolicy(max_records=4, max_bytes=10_000),
    )
    writer.start()
    assert writer.try_enqueue(_record(1))
    assert writer.try_enqueue(_record(2))
    writer.request_stop(drain=True)
    assert writer.wait(2.0)
    snapshot = writer.snapshot()
    assert output.records == [1, 2]
    assert output.closed
    assert snapshot.written_records == 2
    assert snapshot.queued_records == 0
    assert snapshot.inflight_records == 0
    assert snapshot.error == ""


def test_failed_append_is_explicitly_accounted_as_write_failure() -> None:
    output = _FakeOutput([], fail_append=True)
    writer = LoggerWriterWorker(
        lambda: output,
        BufferPolicy(max_records=4, max_bytes=10_000),
    )
    writer.start()
    assert writer.try_enqueue(_record(1))
    assert writer.wait(2.0)
    snapshot = writer.snapshot()
    assert snapshot.written_records == 0
    assert snapshot.write_failed_records == 1
    assert snapshot.dropped_records == 1
    assert snapshot.inflight_records == 0
    assert "disk write failed" in snapshot.error


def test_after_write_failure_does_not_reclassify_durable_record_as_unwritten() -> None:
    output = _FakeOutput([])

    def fail_after_write(_output) -> None:
        raise RuntimeError("retention callback failed")

    writer = LoggerWriterWorker(
        lambda: output,
        BufferPolicy(max_records=4, max_bytes=10_000),
        after_write=fail_after_write,
    )
    writer.start()
    assert writer.try_enqueue(_record(1))
    assert writer.wait(2.0)
    snapshot = writer.snapshot()
    assert output.records == [1]
    assert snapshot.written_records == 1
    assert snapshot.write_failed_records == 0
    assert "retention callback failed" in snapshot.error
