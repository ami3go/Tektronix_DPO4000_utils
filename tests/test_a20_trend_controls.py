from __future__ import annotations

import csv
from pathlib import Path

import pytest

from dpo4000_utils.control import build_measurement_unit_query
from dpo4000_utils.trend import MeasurementTrendModel, TrendValidationError


def test_unit_query_builder() -> None:
    assert build_measurement_unit_query(3) == "MEASUREMENT:MEAS3:UNITS?"
    with pytest.raises(ValueError):
        build_measurement_unit_query(9)


def test_window_keeps_last_seconds_relative_to_newest_sample_across_series() -> None:
    model = MeasurementTrendModel(capacity=100)
    for second in range(10):
        model.append("MEAS1", float(second), timestamp_s=float(second))
    model.append("MEAS2", 42.0, timestamp_s=3.0)

    snapshots = {snap.name: snap for snap in model.snapshots(window_s=4.0)}
    assert [sample.timestamp_s for sample in snapshots["MEAS1"].samples] == [5.0, 6.0, 7.0, 8.0, 9.0]
    # MEAS2's only sample is older than the shared window, so it is hidden.
    assert snapshots["MEAS2"].samples == ()
    # Storage is untouched and counters still describe the whole series.
    assert snapshots["MEAS1"].total_received == 10
    assert model.total_stored_samples == 11


def test_window_is_applied_before_decimation() -> None:
    model = MeasurementTrendModel(capacity=10_000)
    for index in range(10_000):
        model.append("MEAS1", float(index), timestamp_s=float(index))
    (snapshot,) = model.snapshots(max_points=100, window_s=500.0)
    assert snapshot.count <= 100
    assert snapshot.samples[0].timestamp_s >= 9_499.0
    assert snapshot.samples[-1].timestamp_s == 9_999.0


@pytest.mark.parametrize("window", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_window_rejected(window: float) -> None:
    model = MeasurementTrendModel(capacity=10)
    model.append("MEAS1", 1.0, timestamp_s=1.0)
    with pytest.raises(TrendValidationError):
        model.snapshots(window_s=window)


def test_latest_timestamp_and_empty_window() -> None:
    model = MeasurementTrendModel(capacity=10)
    assert model.latest_timestamp_s() is None
    assert model.snapshots(window_s=5.0) == ()
    model.append("MEAS1", 1.0, timestamp_s=2.5)
    assert model.latest_timestamp_s() == 2.5


class _Scope:
    def __init__(self) -> None:
        self.reads = 0

    def read_measurement_value(self, slot: int) -> str:
        self.reads += 1
        return f"{slot}.5E0"

    def read_measurement_unit(self, slot: int) -> str | None:
        return {1: "V", 2: "Hz"}.get(slot)


def _run_action_with(scope: _Scope):
    def run_action(label, execute, *, on_success, on_error, retain_session=False):
        try:
            result = execute(scope)
        except Exception as exc:
            on_error(exc)
        else:
            on_success(result)

    return run_action


@pytest.fixture
def qt_app():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _panel(scope: _Scope):
    from dpo4000_utils.gui_qt.composition.pages.trend import MeasurementTrendPanel

    panel = MeasurementTrendPanel(run_action=_run_action_with(scope))
    panel.slot_checks[1].setChecked(True)  # MEAS1 + MEAS2
    return panel


def test_freeze_holds_picture_while_polling_continues(qt_app) -> None:
    scope = _Scope()
    panel = _panel(scope)
    panel.start()
    frozen_before = panel.plot._frozen
    assert frozen_before is None
    panel.freeze_checkbox.setChecked(True)
    held = panel.plot._frozen
    assert held is not None and {snap.name for snap in held} == {"MEAS1", "MEAS2"}

    panel._poll_once()
    assert panel._model.total_stored_samples == 4  # acquisition kept going
    assert panel.plot._frozen is held  # display did not change

    panel.freeze_checkbox.setChecked(False)
    assert panel.plot._frozen is None
    panel.stop()
    panel.deleteLater()


def test_units_are_read_once_at_start_for_legend(qt_app) -> None:
    panel = _panel(_Scope())
    panel.start()
    assert panel.plot._units == {"MEAS1": "V", "MEAS2": "Hz"}
    panel.stop()
    panel.deleteLater()


def test_csv_logging_reuses_single_read_on_worker(qt_app, tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QFileDialog

    target = tmp_path / "trend.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), ""))
    scope = _Scope()
    panel = _panel(scope)
    panel.log_checkbox.setChecked(True)
    panel.start()  # prompts for the CSV path, then polls once
    panel._poll_once()
    panel.stop()

    assert scope.reads == 4  # two polls x two slots, no duplicate reads for logging
    assert panel._model.total_stored_samples == 4
    with target.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["utc_timestamp", "local_timestamp", "elapsed_s", "MEAS1", "MEAS2"]
    assert [row[3:] for row in rows[1:]] == [["1.5E0", "2.5E0"], ["1.5E0", "2.5E0"]]
    assert panel.log_checkbox.isEnabled()
    panel.deleteLater()


def test_logging_without_path_does_not_start(qt_app, monkeypatch) -> None:
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("", ""))
    panel = _panel(_Scope())
    panel.log_checkbox.setChecked(True)
    panel.start()
    assert not panel._timer.isActive()
    assert panel.start_button.isEnabled()
    assert "CSV" in panel.status_label.text()
    panel.deleteLater()


def test_window_selector_drives_plot(qt_app) -> None:
    panel = _panel(_Scope())
    index = panel.window_combo.findText("10 min")
    panel.window_combo.setCurrentIndex(index)
    assert panel.plot._window_s == 600.0
    panel.deleteLater()
