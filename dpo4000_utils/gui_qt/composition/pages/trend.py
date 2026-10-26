"""A20 Measurement Trend Dashboard attached to the existing Measurement page."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path
import time
from typing import Any, Callable

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ....automation.measurement_logging import append_measurement_row
from ....trend import DEFAULT_RENDER_POINTS, MeasurementTrendModel, TrendSnapshot

_WINDOW_CHOICES: tuple[tuple[str, float | None], ...] = (
    ("All", None),
    ("1 min", 60.0),
    ("10 min", 600.0),
    ("1 h", 3600.0),
)


class TrendPlotWidget(QWidget):
    """Lightweight Qt painter for already-decimated trend snapshots."""

    def __init__(self, model: MeasurementTrendModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("measurementTrendPlot")
        self._model = model
        self._render_points = DEFAULT_RENDER_POINTS
        self._window_s: float | None = None
        self._frozen: tuple[TrendSnapshot, ...] | None = None
        self._units: dict[str, str] = {}
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_render_points(self, count: int) -> None:
        self._render_points = max(2, int(count))
        self.update()

    def set_window(self, seconds: float | None) -> None:
        self._window_s = seconds
        self.update()

    def set_units(self, units: dict[str, str]) -> None:
        self._units = dict(units)
        self.update()

    def set_model(self, model: MeasurementTrendModel) -> None:
        self._model = model
        if self._frozen is not None:
            self._frozen = ()
        self.update()

    def set_frozen(self, frozen: bool) -> None:
        """Hold the current picture while acquisition and logging continue."""
        self._frozen = self._current_snapshots() if frozen else None
        self.update()

    @property
    def is_frozen(self) -> bool:
        return self._frozen is not None

    def _current_snapshots(self) -> tuple[TrendSnapshot, ...]:
        return tuple(
            snap
            for snap in self._model.snapshots(
                max_points=self._render_points,
                window_s=self._window_s,
            )
            if snap.samples
        )

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bounds = QRectF(self.rect()).adjusted(50.0, 15.0, -15.0, -35.0)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.base())
        painter.setPen(QPen(palette.mid().color(), 1.0))
        painter.drawRect(bounds)

        snapshots = self._frozen if self._frozen is not None else self._current_snapshots()
        if not snapshots:
            painter.setPen(palette.text().color())
            painter.drawText(bounds, Qt.AlignmentFlag.AlignCenter, "No trend samples")
            return

        all_samples = [sample for snap in snapshots for sample in snap.samples]
        min_t = min(sample.timestamp_s for sample in all_samples)
        max_t = max(sample.timestamp_s for sample in all_samples)
        min_y = min(sample.value for sample in all_samples)
        max_y = max(sample.value for sample in all_samples)
        if max_t <= min_t:
            max_t = min_t + 1.0
        if max_y <= min_y:
            pad = max(1.0, abs(min_y) * 0.01)
            min_y -= pad
            max_y += pad

        painter.setPen(palette.text().color())
        painter.drawText(5, 25, f"{max_y:.6g}")
        painter.drawText(5, int(bounds.bottom()), f"{min_y:.6g}")
        painter.drawText(
            int(bounds.left()),
            int(self.height() - 8),
            f"{max_t - min_t:.3f} s window" + (" — frozen" if self._frozen is not None else ""),
        )

        legend_x = int(bounds.left())
        legend_y = 28
        for index, snapshot in enumerate(snapshots):
            color = QColor.fromHsv((index * 67) % 360, 190, 220)
            pen = QPen(color, 1.5)
            painter.setPen(pen)
            path = QPainterPath()
            for point_index, sample in enumerate(snapshot.samples):
                x = bounds.left() + (sample.timestamp_s - min_t) / (max_t - min_t) * bounds.width()
                y = bounds.bottom() - (sample.value - min_y) / (max_y - min_y) * bounds.height()
                point = QPointF(x, y)
                if point_index == 0:
                    path.moveTo(point)
                else:
                    path.lineTo(point)
            painter.drawPath(path)
            unit = self._units.get(snapshot.name)
            painter.drawText(legend_x, legend_y, f"{snapshot.name} [{unit}]" if unit else snapshot.name)
            legend_x += 80
            if legend_x > bounds.right() - 80:
                legend_x = int(bounds.left())
                legend_y += 18


class MeasurementTrendPanel(QGroupBox):
    """Poll selected MEAS slots asynchronously into a bounded trend model."""

    def __init__(
        self,
        *,
        run_action: Callable[..., Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Measurement Trend Dashboard (A20)", parent)
        self.setObjectName("measurementTrendPanel")
        self._run_action = run_action
        self._model = MeasurementTrendModel()
        self._poll_in_flight = False
        self._skipped_ticks = 0
        self._accepted_batches = 0
        self._last_model_update_ms = 0.0
        self._log_path: Path | None = None
        self._log_started_utc: datetime | None = None
        self._last_log_error = ""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_once)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Poll selected MEAS slots through the serialized scope worker. Slow reads do not "
            "queue up: while one poll is active, later timer ticks are counted and skipped."
        )
        hint.setWordWrap(True)
        hint.setObjectName("MutedLabel")
        layout.addWidget(hint)

        slots = QGridLayout()
        self.slot_checks: list[QCheckBox] = []
        for index in range(8):
            check = QCheckBox(f"MEAS{index + 1}")
            check.setObjectName(f"measurementTrendSlot{index + 1}")
            check.setChecked(index == 0)
            self.slot_checks.append(check)
            slots.addWidget(check, index // 4, index % 4)
        layout.addLayout(slots)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Poll"))
        self.interval_combo = QComboBox()
        self.interval_combo.setObjectName("measurementTrendInterval")
        for label, milliseconds in (
            ("250 ms", 250),
            ("500 ms", 500),
            ("1 s", 1000),
            ("2 s", 2000),
            ("5 s", 5000),
        ):
            self.interval_combo.addItem(label, milliseconds)
        self.interval_combo.setCurrentIndex(2)
        controls.addWidget(self.interval_combo)

        controls.addWidget(QLabel("Capacity"))
        self.capacity_combo = QComboBox()
        self.capacity_combo.setObjectName("measurementTrendCapacity")
        for count in (1_000, 10_000, 100_000):
            self.capacity_combo.addItem(f"{count:,}", count)
        self.capacity_combo.setCurrentIndex(2)
        controls.addWidget(self.capacity_combo)

        controls.addWidget(QLabel("Render"))
        self.render_combo = QComboBox()
        self.render_combo.setObjectName("measurementTrendRenderPoints")
        for count in (500, 1_000, 2_000, 5_000):
            self.render_combo.addItem(f"{count:,}", count)
        self.render_combo.setCurrentIndex(2)
        controls.addWidget(self.render_combo)

        controls.addWidget(QLabel("Window"))
        self.window_combo = QComboBox()
        self.window_combo.setObjectName("measurementTrendWindow")
        for label, seconds in _WINDOW_CHOICES:
            self.window_combo.addItem(label, seconds)
        controls.addWidget(self.window_combo)
        controls.addStretch(1)
        layout.addLayout(controls)

        logging_row = QHBoxLayout()
        self.log_checkbox = QCheckBox("Log to CSV")
        self.log_checkbox.setObjectName("measurementTrendLogCsv")
        self.log_checkbox.setToolTip(
            "Append each poll to a CSV file on the scope worker (same format as Automation A5)"
        )
        self.log_path_button = QPushButton("Choose CSV…")
        self.log_path_button.setObjectName("measurementTrendLogPath")
        self.log_path_label = QLabel("No log file")
        self.log_path_label.setObjectName("measurementTrendLogLabel")
        self.log_path_button.clicked.connect(self._choose_log_path)
        logging_row.addWidget(self.log_checkbox)
        logging_row.addWidget(self.log_path_button)
        logging_row.addWidget(self.log_path_label, 1)
        layout.addLayout(logging_row)

        actions = QHBoxLayout()
        self.start_button = QPushButton("Start Trend")
        self.start_button.setObjectName("measurementTrendStart")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("measurementTrendStop")
        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("measurementTrendClear")
        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.stop)
        self.clear_button.clicked.connect(self.clear)
        self.freeze_checkbox = QCheckBox("Freeze display")
        self.freeze_checkbox.setObjectName("measurementTrendFreeze")
        self.freeze_checkbox.setToolTip("Hold the plot while polling and logging continue")
        self.freeze_checkbox.toggled.connect(self._freeze_toggled)
        actions.addWidget(self.start_button)
        actions.addWidget(self.stop_button)
        actions.addWidget(self.clear_button)
        actions.addWidget(self.freeze_checkbox)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.plot = TrendPlotWidget(self._model, self)
        layout.addWidget(self.plot)
        self.status_label = QLabel("Stopped — 0 samples")
        self.status_label.setObjectName("measurementTrendStatus")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.interval_combo.currentIndexChanged.connect(self._interval_changed)
        self.capacity_combo.currentIndexChanged.connect(self._capacity_changed)
        self.render_combo.currentIndexChanged.connect(self._render_changed)
        self.window_combo.currentIndexChanged.connect(self._window_changed)
        self.stop_button.setEnabled(False)

    def _selected_slots(self) -> tuple[int, ...]:
        return tuple(index + 1 for index, check in enumerate(self.slot_checks) if check.isChecked())

    def start(self) -> None:
        slots = self._selected_slots()
        if not slots:
            self.status_label.setText("Select at least one MEAS slot")
            return
        if self.log_checkbox.isChecked():
            if self._log_path is None and not self._choose_log_path():
                self.status_label.setText("Choose a CSV file or disable Log to CSV")
                return
            self._log_started_utc = datetime.now(timezone.utc)
        else:
            self._log_started_utc = None
        self._last_log_error = ""
        self._set_logging_controls_enabled(False)
        self._timer.start(int(self.interval_combo.currentData()))
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self._read_units(slots)
        self._poll_once()

    def stop(self) -> None:
        self._timer.stop()
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self._set_logging_controls_enabled(True)
        self._log_started_utc = None
        self._update_status(prefix="Stopped")

    def _set_logging_controls_enabled(self, enabled: bool) -> None:
        self.log_checkbox.setEnabled(enabled)
        self.log_path_button.setEnabled(enabled)

    def _choose_log_path(self) -> bool:
        filename, _filter = QFileDialog.getSaveFileName(
            self,
            "Measurement trend CSV log",
            "measurement_trend.csv",
            "CSV files (*.csv);;All files (*)",
        )
        if not filename:
            return False
        self._log_path = Path(filename)
        self.log_path_label.setText(str(self._log_path))
        return True

    def _read_units(self, slots: tuple[int, ...]) -> None:
        def execute(scope: Any) -> dict[str, str]:
            reader = getattr(scope, "read_measurement_unit", None)
            if reader is None:
                return {}
            units: dict[str, str] = {}
            for slot in slots:
                unit = reader(slot)
                if unit:
                    units[f"MEAS{slot}"] = unit
            return units

        def success(result: Any) -> None:
            if isinstance(result, dict):
                self.plot.set_units({str(key): str(value) for key, value in result.items()})

        def failure(_exc: Exception) -> None:
            # Units are display labels only; a failed read leaves the legend unlabeled.
            self.plot.set_units({})

        self._run_action(
            "A20 measurement units",
            execute,
            on_success=success,
            on_error=failure,
            retain_session=True,
        )

    def _freeze_toggled(self, frozen: bool) -> None:
        self.plot.set_frozen(frozen)

    def _window_changed(self) -> None:
        self.plot.set_window(self.window_combo.currentData())
        if self.plot.is_frozen:
            self.plot.set_frozen(True)

    def clear(self) -> None:
        self._model.clear()
        self._accepted_batches = 0
        self._skipped_ticks = 0
        if self.plot.is_frozen:
            self.plot.set_frozen(True)
        self.plot.update()
        self._update_status(prefix="Running" if self._timer.isActive() else "Stopped")

    def _interval_changed(self) -> None:
        if self._timer.isActive():
            self._timer.setInterval(int(self.interval_combo.currentData()))

    def _capacity_changed(self) -> None:
        # Capacity changes are explicit resets so bounded-memory semantics stay simple.
        was_running = self._timer.isActive()
        self._model = MeasurementTrendModel(int(self.capacity_combo.currentData()))
        self.plot.set_model(self._model)
        self._accepted_batches = 0
        self._skipped_ticks = 0
        self.plot.update()
        self._update_status(prefix="Running" if was_running else "Stopped")

    def _render_changed(self) -> None:
        self.plot.set_render_points(int(self.render_combo.currentData()))

    @staticmethod
    def _parse_measurement_value(value: Any) -> float:
        token = str(value).strip().split()[-1]
        number = float(token)
        if not math.isfinite(number):
            raise ValueError("measurement is not finite")
        return number

    def _poll_once(self) -> None:
        if self._poll_in_flight:
            self._skipped_ticks += 1
            self._update_status(prefix="Running")
            return
        slots = self._selected_slots()
        if not slots:
            self.stop()
            self.status_label.setText("Stopped — select at least one MEAS slot")
            return
        self._poll_in_flight = True
        requested_at = time.perf_counter()
        log_path = self._log_path if self._log_started_utc is not None else None
        log_started_utc = self._log_started_utc

        def execute(scope: Any) -> dict[str, Any]:
            if log_path is not None and log_started_utc is not None:
                # Read once and append the same values on the worker thread.
                logged = append_measurement_row(
                    scope,
                    log_path,
                    slots,
                    run_started_utc=log_started_utc,
                )
                return {
                    "values": {f"MEAS{slot}": value for slot, value in logged.values.items()},
                    "log_error": logged.error,
                }
            return {
                "values": {
                    f"MEAS{slot}": scope.read_measurement_value(slot)
                    for slot in slots
                },
                "log_error": "",
            }

        def success(result: Any) -> None:
            self._poll_in_flight = False
            started = time.perf_counter()
            accepted: dict[str, float] = {}
            values = result.get("values") if isinstance(result, dict) else None
            if isinstance(result, dict):
                self._last_log_error = str(result.get("log_error") or "")
            if isinstance(values, dict):
                for name, raw_value in values.items():
                    try:
                        accepted[str(name)] = self._parse_measurement_value(raw_value)
                    except (ValueError, TypeError, IndexError):
                        continue
            if accepted:
                self._model.append_many(accepted, timestamp_s=time.time())
                self._accepted_batches += 1
            self._last_model_update_ms = (time.perf_counter() - started) * 1000.0
            self.plot.update()
            latency_ms = (time.perf_counter() - requested_at) * 1000.0
            self._update_status(prefix="Running", poll_latency_ms=latency_ms)

        def failure(exc: Exception) -> None:
            self._poll_in_flight = False
            self.status_label.setText(f"Trend poll failed: {exc}")

        self._run_action(
            "A20 measurement trend poll",
            execute,
            on_success=success,
            on_error=failure,
            retain_session=True,
        )

    def _update_status(self, *, prefix: str, poll_latency_ms: float | None = None) -> None:
        parts = [
            prefix,
            f"stored {self._model.total_stored_samples:,} samples",
            f"batches {self._accepted_batches:,}",
            f"skipped ticks {self._skipped_ticks:,}",
            f"model update {self._last_model_update_ms:.3f} ms",
        ]
        if poll_latency_ms is not None:
            parts.append(f"poll {poll_latency_ms:.1f} ms")
        if self._log_started_utc is not None and self._log_path is not None:
            parts.append(f"CSV log error: {self._last_log_error}" if self._last_log_error else "logging CSV")
        self.status_label.setText(" — ".join(parts))


def attach_measurement_trend_panel(host: Any, page: QWidget) -> QWidget:
    """Attach A20 trend controls to the mature Measurement page."""
    # A scroll-area page's own layout() is its internal viewport layout; attach to
    # the scrolled body instead so the panel stacks with the other cards.
    body = page.widget() if isinstance(page, QScrollArea) else page
    layout = body.layout()
    if layout is None:
        layout = QVBoxLayout(body)
    panel = MeasurementTrendPanel(run_action=host._run_action, parent=body)
    panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    last = layout.count() - 1
    if last >= 0 and layout.itemAt(last).spacerItem() is not None:
        layout.insertWidget(last, panel)
    else:
        layout.addWidget(panel)
    return page


__all__ = [
    "MeasurementTrendPanel",
    "TrendPlotWidget",
    "attach_measurement_trend_panel",
]
