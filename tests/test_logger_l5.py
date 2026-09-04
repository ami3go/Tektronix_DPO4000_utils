from __future__ import annotations

import csv
from datetime import datetime, timezone

from dpo4000_utils.logger.measurement_csv import MeasurementCsvStreamWriter
from dpo4000_utils.logger.models import LoggerConfig, LoggerMode, LoggerRecord
from dpo4000_utils.logger.producer import capture_logger_record


def test_measurement_config_requires_slots() -> None:
    try:
        LoggerConfig(mode=LoggerMode.MEASUREMENTS, waveform_sources=(), measurement_slots=())
    except ValueError as exc:
        assert "MEAS" in str(exc)
    else:
        raise AssertionError("measurement mode accepted no slots")


def test_measurement_producer_keeps_fixed_slots_and_capture_timestamp() -> None:
    class Scope:
        def read_measurement_value(self, slot):
            if slot == 2:
                return "9.9E37"
            return str(slot * 1.5)

    record = capture_logger_record(
        Scope(),
        LoggerConfig(mode=LoggerMode.MEASUREMENTS, waveform_sources=(), measurement_slots=(1, 2)),
        1,
    )
    assert record.measurements[1] == 1.5
    assert record.measurements[2] is None
    assert 2 in record.measurement_errors
    assert record.captured_monotonic > 0
    parsed = datetime.fromisoformat(record.captured_utc)
    assert parsed.tzinfo is not None


def test_measurement_csv_uses_capture_time_not_writer_time(tmp_path) -> None:
    path = tmp_path / "measurements.csv"
    writer = MeasurementCsvStreamWriter(path, (1, 2))
    first_utc = "2026-09-04T10:00:00+00:00"
    second_utc = "2026-09-04T10:00:02+00:00"
    writer.append(
        LoggerRecord(
            sequence=1,
            captured_utc=first_utc,
            captured_monotonic=100.0,
            measurements={1: 3.0, 2: None},
            measurement_errors={2: "unavailable"},
        )
    )
    writer.append(
        LoggerRecord(
            sequence=2,
            captured_utc=second_utc,
            captured_monotonic=102.0,
            measurements={1: 4.0, 2: 5.0},
        )
    )
    writer.close()

    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert rows[0][4:6] == ["MEAS1", "MEAS2"]
    assert rows[1][0] == first_utc
    assert rows[1][1] == datetime.fromisoformat(first_utc).astimezone().isoformat()
    assert rows[1][2] == "0.000000000"
    assert rows[2][0] == second_utc
    assert rows[2][2] == "2.000000000"
    assert rows[1][4] == "3.0"
    assert rows[1][5] == ""
