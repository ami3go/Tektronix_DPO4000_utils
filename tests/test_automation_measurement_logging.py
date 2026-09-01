from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dpo4000_utils.automation.measurement_logging import (
    append_measurement_row,
    normalize_measurement_slots,
)
from dpo4000_utils.errors import DPOTransportError


class _FakeScope:
    def __init__(self, values: dict[int, object] | None = None) -> None:
        self.values = values or {}
        self.calls: list[int] = []

    def read_measurement_value(self, slot: int) -> str:
        self.calls.append(slot)
        value = self.values.get(slot, f"{slot}.0")
        if isinstance(value, Exception):
            raise value
        return str(value)


def test_measurement_slot_validation_preserves_order_and_deduplicates() -> None:
    assert normalize_measurement_slots([3, 1, 3, 8]) == (3, 1, 8)
    with pytest.raises(ValueError, match="at least one"):
        normalize_measurement_slots([])
    with pytest.raises(ValueError, match="MEAS1 and MEAS8"):
        normalize_measurement_slots([9])


def test_a5_appends_fixed_columns_and_keeps_one_csv(tmp_path: Path) -> None:
    path = tmp_path / "measurements.csv"
    started = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
    scope = _FakeScope({1: "1.25", 3: "3.5"})

    first = append_measurement_row(
        scope,
        path,
        [1, 3],
        run_started_utc=started,
        now_utc=datetime(2026, 9, 1, 10, 0, 1, tzinfo=timezone.utc),
    )
    second = append_measurement_row(
        scope,
        path,
        [1, 3],
        run_started_utc=started,
        now_utc=datetime(2026, 9, 1, 10, 0, 2, tzinfo=timezone.utc),
    )

    assert first.success and second.success
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["utc_timestamp", "local_timestamp", "elapsed_s", "MEAS1", "MEAS3"]
    assert rows[1][2:] == ["1.000000", "1.25", "3.5"]
    assert rows[2][2:] == ["2.000000", "1.25", "3.5"]


def test_a5_non_transport_slot_failure_keeps_column_empty(tmp_path: Path) -> None:
    path = tmp_path / "measurements.csv"
    scope = _FakeScope({1: ValueError("measurement unavailable"), 2: "2.0"})

    result = append_measurement_row(
        scope,
        path,
        [1, 2],
        run_started_utc=datetime.now(timezone.utc),
    )

    assert result.success is True
    assert result.values[1] == ""
    assert "measurement unavailable" in result.slot_errors[1]
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows[-1][-2:] == ["", "2.0"]


def test_a5_transport_failure_propagates(tmp_path: Path) -> None:
    scope = _FakeScope({1: DPOTransportError("lost")})

    with pytest.raises(DPOTransportError, match="lost"):
        append_measurement_row(
            scope,
            tmp_path / "measurements.csv",
            [1],
            run_started_utc=datetime.now(timezone.utc),
        )


def test_a5_gui_stays_behind_public_driver_boundary() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "dpo4000_utils" / "gui_qt" / "automation_measurement_window.py").read_text(
        encoding="utf-8"
    )

    assert "append_measurement_row(" in source
    assert ".query(" not in source
    assert ".write(" not in source
    assert "MEASUREMENT:" not in source
