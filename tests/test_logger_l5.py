from __future__ import annotations

import csv

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


def test_measurement_producer_keeps_fixed_slots_and_unavailable_values() -> None:
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


def test_measurement_csv_has_fixed_columns(tmp_path) -> None:
    path = tmp_path / "measurements.csv"
    writer = MeasurementCsvStreamWriter(path, (1, 2))
    writer.append(LoggerRecord(sequence=1, captured_utc="utc", measurements={1: 3.0, 2: None}, measurement_errors={2: "unavailable"}))
    writer.close()
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert rows[0][4:6] == ["MEAS1", "MEAS2"]
    assert rows[1][4] == "3.0"
    assert rows[1][5] == ""
