from __future__ import annotations

import time

import pytest

from dpo4000_utils.logger.buffering import BufferPolicy, LoggerWriterWorker


class _LateOutput:
    current_paths = ()
    bytes_written = 0
    segment_index = 0
    rotation_count = 0
    current_segment_bytes = 0

    def append(self, _record) -> None:
        raise AssertionError("Timed-out writer must not accept records")

    def close(self) -> None:
        return None


def test_writer_start_timeout_revokes_future_acceptance() -> None:
    def slow_factory():
        time.sleep(0.2)
        return _LateOutput()

    writer = LoggerWriterWorker(
        slow_factory,
        BufferPolicy(max_records=2, max_bytes=4096),
    )
    with pytest.raises(TimeoutError):
        writer.start(ready_timeout_s=0.1)
    assert not writer.has_capacity()
    assert writer.wait(1.0)
