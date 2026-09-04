from __future__ import annotations

import csv

from dpo4000_utils.logger.mixed_csv import MixedCsvStreamWriter
from dpo4000_utils.logger.models import LoggerRecord


def test_mixed_csv_frames_complete_record_with_end_marker(tmp_path) -> None:
    path = tmp_path / "mixed.csv"
    writer = MixedCsvStreamWriter(path)
    writer.append(
        LoggerRecord(
            sequence=7,
            captured_utc="2026-09-04T10:00:00+00:00",
            captured_monotonic=100.0,
            measurements={1: 1.25},
            metadata={"partial": False},
        )
    )
    writer.close()

    rows = list(csv.reader(path.open(encoding="utf-8")))
    types = [row[0] for row in rows[1:]]
    assert types == ["RECORD_BEGIN", "MEAS", "RECORD_END"]
    assert rows[-1][6] == "complete"
    assert writer.records_written == 1


def test_mixed_csv_begin_marker_is_not_a_completion_marker(tmp_path) -> None:
    path = tmp_path / "mixed.csv"
    writer = MixedCsvStreamWriter(path)
    # This test deliberately writes only the framing row that would survive if a
    # process died after record start. Recovery code can therefore require END.
    writer._writer.writerow(  # noqa: SLF001 - deliberate crash-framing test.
        ["RECORD_BEGIN", 1, "2026-09-04T10:00:00+00:00", "", "", "", "begin", "{}"]
    )
    writer._handle.flush()  # noqa: SLF001
    writer._handle.close()  # noqa: SLF001
    writer._closed = True  # noqa: SLF001

    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert any(row[0] == "RECORD_BEGIN" for row in rows[1:])
    assert not any(row[0] == "RECORD_END" for row in rows[1:])
