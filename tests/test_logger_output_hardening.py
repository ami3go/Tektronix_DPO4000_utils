from __future__ import annotations

import pytest

from dpo4000_utils.logger.models import LoggerMode, LoggerOutputFormat, LoggerRecord
from dpo4000_utils.logger.output import LoggerOutputSession


def _measurement_record(sequence: int = 1) -> LoggerRecord:
    return LoggerRecord(
        sequence=sequence,
        captured_utc="2026-09-04T10:00:00+00:00",
        captured_monotonic=100.0 + sequence,
        measurements={1: float(sequence)},
    )


def test_segment_is_not_completed_when_writer_close_fails(tmp_path) -> None:
    session = LoggerOutputSession(
        tmp_path,
        LoggerOutputFormat.CSV,
        mode=LoggerMode.MEASUREMENTS,
        measurement_slots=(1,),
    )
    session.append(_measurement_record())
    paths = session.current_paths
    writer = session.csv_writer
    assert writer is not None

    def fail_close() -> None:
        writer._handle.flush()  # noqa: SLF001 - simulated close failure.
        writer._handle.close()  # noqa: SLF001
        writer._closed = True  # noqa: SLF001
        raise OSError("simulated close failure")

    writer.close = fail_close
    with pytest.raises(RuntimeError, match="simulated close failure"):
        session.close()

    assert session.completed_segments == ()
    assert session.failed_segments == (paths,)


def test_partial_both_format_append_taints_segment(tmp_path) -> None:
    session = LoggerOutputSession(
        tmp_path,
        LoggerOutputFormat.BOTH,
        mode=LoggerMode.MEASUREMENTS,
        measurement_slots=(1,),
    )
    paths = session.current_paths
    binary = session.binary_writer
    assert binary is not None

    def fail_append(_record) -> None:
        raise OSError("binary append failed")

    binary.append = fail_append
    with pytest.raises(OSError, match="binary append failed"):
        session.append(_measurement_record())
    session.close()

    assert session.completed_segments == ()
    assert session.failed_segments == (paths,)
