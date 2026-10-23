"""A22 local live-waveform panel; instrument access is via public driver/serialized dispatch."""
from __future__ import annotations

import math
from typing import Any, Callable

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ....live_stream import (
    LiveStreamEngine, StreamConfig, StreamState, WaveformFrame, capture_frame,
)


class LiveWaveformPlot(QWidget):
    """Qt painter for worker-prepared, bounded (<50k points) render traces."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("liveStreamPlot")
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._x: tuple[float, ...] = ()
        self._y: tuple[float, ...] = ()

    def display(self, frame: WaveformFrame) -> None:
        self._x, self._y = frame.render_x, frame.render_y
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.base())
        box = QRectF(self.rect()).adjusted(50, 15, -15, -30)
        painter.setPen(QPen(palette.mid().color(), 1))
        painter.drawRect(box)
        if not self._x:
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, "No live waveform")
            return
        min_x, max_x = self._x[0], self._x[-1]
        min_y, max_y = min(self._y), max(self._y)
        if max_x <= min_x or not all(math.isfinite(v) for v in (min_x, max_x)):
            return
        if not all(math.isfinite(v) for v in (min_y, max_y)):
            return
        if max_y <= min_y:
            padding = max(1e-9, abs(min_y) * 0.01)
            min_y -= padding
            max_y += padding
        path = QPainterPath()
        for i, (x, y) in enumerate(zip(self._x, self._y)):
            pt = QPointF(
                box.left() + (x - min_x) * box.width() / (max_x - min_x),
                box.bottom() - (y - min_y) * box.height() / (max_y - min_y),
            )
            if i == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
        painter.setPen(QPen(palette.highlight().color(), 1.5))
        painter.drawPath(path)
        painter.setPen(palette.text().color())
        painter.drawText(5, 25, f"{max_y:.4g}")
        painter.drawText(5, int(box.bottom()), f"{min_y:.4g}")
        painter.drawText(int(box.left()), self.height() - 7, f"{min_x:.3g} .. {max_x:.3g} s")


class LiveWaveformPanel(QGroupBox):
    """One-in-flight acquisition, latest-frame rendering, explicit Stop/Restart."""

    def __init__(
        self, *, host: Any, run_action: Callable[..., Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Live Waveform (A22)", parent)
        self.setObjectName("liveWaveformPanel")
        self._host = host
        self._run_action = run_action
        self.engine = LiveStreamEngine()
        self._closed = False
        self._cadence = QTimer(self)
        self._cadence.setSingleShot(True)
        self._cadence.timeout.connect(self._acquire_if_due)
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(100)  # bounded 10 FPS regardless of requested acquisition rate
        self._render_timer.timeout.connect(self._refresh)
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Repeated waveform snapshots, not lossless ADC streaming. "
            "At most one scope operation in flight; newer unrendered frames replace older ones."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        self.source_combo = QComboBox()
        self.source_combo.setObjectName("liveStreamSource")
        self.source_combo.addItems(("CH1", "CH2", "CH3", "CH4"))
        form.addRow("Source", self.source_combo)
        self.points_combo = QComboBox()
        self.points_combo.setObjectName("liveStreamPoints")
        for label, value in (("1k", 1_000), ("10k", 10_000),
                             ("100k", 100_000), ("1M", 1_000_000), ("Full", None)):
            self.points_combo.addItem(label, value)
        self.points_combo.setCurrentIndex(1)
        form.addRow("Transfer", self.points_combo)
        self.rate_combo = QComboBox()
        self.rate_combo.setObjectName("liveStreamTargetRate")
        for hz in (1, 2, 5, 10, 20, 100):
            self.rate_combo.addItem("Maximum" if hz == 100 else f"{hz} Hz", float(hz))
        self.rate_combo.setCurrentIndex(2)
        form.addRow("Requested rate", self.rate_combo)
        self.render_combo = QComboBox()
        self.render_combo.setObjectName("liveStreamRenderPoints")
        for count in (500, 1_000, 2_000, 5_000, 10_000):
            self.render_combo.addItem(f"{count:,}", count)
        self.render_combo.setCurrentIndex(2)
        form.addRow("Render points", self.render_combo)
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("liveStreamStartButton")
        self.pause_button = QPushButton("Pause")
        self.pause_button.setObjectName("liveStreamPauseButton")
        self.resume_button = QPushButton("Resume")
        self.resume_button.setObjectName("liveStreamResumeButton")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("liveStreamStopButton")
        for button, callback in (
            (self.start_button, self.start), (self.pause_button, self.pause),
            (self.resume_button, self.resume), (self.stop_button, self.stop),
        ):
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.plot = LiveWaveformPlot(self)
        layout.addWidget(self.plot)
        self.state_label = QLabel()
        self.state_label.setObjectName("liveStreamStateLabel")
        self.stats_label = QLabel()
        self.stats_label.setObjectName("liveStreamStatsLabel")
        self.stats_label.setWordWrap(True)
        self.error_label = QLabel()
        self.error_label.setObjectName("liveStreamErrorLabel")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.state_label)
        layout.addWidget(self.stats_label)
        layout.addWidget(self.error_label)

    def _configuration(self) -> StreamConfig:
        return StreamConfig(
            source=self.source_combo.currentText(),
            point_count=self.points_combo.currentData(),
            target_hz=float(self.rate_combo.currentData()),
            render_points=int(self.render_combo.currentData()),
        )

    def start(self) -> None:
        if self._closed:
            return
        if bool(getattr(self._host, "_operation_active", False)) or bool(
            getattr(self._host, "_automation_any_active", lambda: False)()
        ):
            self.error_label.setText("Cannot start: another scope operation is active")
            return
        try:
            self.engine.start(self._configuration())
        except (ValueError, RuntimeError) as exc:
            self.error_label.setText(str(exc))
            return
        self._host._composition_live_lease = True
        self._render_timer.start()
        self._schedule()
        self._refresh()

    def pause(self) -> None:
        if self.engine.state not in {StreamState.STARTING, StreamState.RUNNING}:
            return
        self.engine.pause()
        self._cadence.stop()
        self._refresh()

    def resume(self) -> None:
        if self.engine.state is not StreamState.PAUSED:
            return
        self.engine.resume()
        self._schedule()
        self._refresh()

    def stop(self) -> None:
        self._cadence.stop()
        self._render_timer.stop()
        self.engine.stop()  # invalidates callbacks; physical transfer may still time out
        self._host._composition_live_lease = False
        self._refresh()

    def shutdown(self) -> None:
        self._closed = True
        self.stop()

    def _schedule(self) -> None:
        if self._closed:
            return
        delay = self.engine.due_in()
        if delay is not None:
            self._cadence.start(max(0, math.ceil(delay * 1000)))

    def _acquire_if_due(self) -> None:
        if self._closed:
            return
        token = self.engine.begin_due()
        if token is None:
            self._schedule()
            return
        config = self.engine.config

        def execute(scope: Any) -> WaveformFrame:
            return capture_frame(scope, config, token[0], token[1])

        def success(result: Any) -> None:
            if not isinstance(result, WaveformFrame):
                self.engine.fail(token, TypeError("Driver returned invalid frame"))
            else:
                self.engine.complete(token, result)
            if self.engine.state is StreamState.ERROR:
                self._host._composition_live_lease = False
            self._schedule()
            self._refresh_status()

        def failure(exc: BaseException) -> None:
            self.engine.fail(token, exc)
            if self.engine.state is StreamState.ERROR:
                self._host._composition_live_lease = False
            self._schedule()
            self._refresh_status()

        self._run_action(
            "A22 live waveform snapshot", execute,
            on_success=success, on_error=failure, retain_session=True,
        )

    def _refresh(self) -> None:
        frame = self.engine.take_latest()
        if frame is not None and self.engine.state in {
            StreamState.RUNNING, StreamState.PAUSED
        }:
            self.plot.display(frame)
        self._refresh_status()

    def _refresh_status(self) -> None:
        state = self.engine.state
        self.state_label.setText(f"State: {state.value} | requested {self.engine.config.target_hz:g} Hz")
        self.start_button.setEnabled(state in {StreamState.IDLE, StreamState.ERROR} and not self._closed)
        self.pause_button.setEnabled(state in {StreamState.STARTING, StreamState.RUNNING})
        self.resume_button.setEnabled(state is StreamState.PAUSED)
        self.stop_button.setEnabled(state not in {StreamState.IDLE})
        stats = self.engine.stats()
        self.stats_label.setText(
            f"Acq {stats.acquisition_fps:.2f} FPS | render {stats.render_fps:.2f} FPS | "
            f"samples/frame {self.engine.config.point_count or 'full'} | "
            f"latest {stats.latest_acquisition_s * 1000:.1f} ms | "
            f"p50/p95/p99 {stats.p50_acquisition_s * 1000:.1f}/"
            f"{stats.p95_acquisition_s * 1000:.1f}/{stats.p99_acquisition_s * 1000:.1f} ms | "
            f"{stats.transfer_bytes_per_s / 1e6:.2f} MB/s | "
            f"acquired {stats.frames_acquired} | rendered {stats.frames_rendered} | "
            f"replaced {stats.frames_replaced} | skipped {stats.deadlines_skipped} | "
            f"errors {stats.acquisition_errors} | reconnects {stats.reconnect_count}"
        )
        if stats.last_error:
            self.error_label.setText(stats.last_error)


def attach_live_waveform_panel(host: Any, page: QWidget) -> QWidget:
    """Attach under Measurement beside A20, without new top-level navigation."""
    body = page.widget() if isinstance(page, QScrollArea) else page
    layout = body.layout()
    if layout is None:
        layout = QVBoxLayout(body)
    panel = LiveWaveformPanel(host=host, run_action=host._run_action, parent=body)
    host._composition_live_stream_panel = panel
    panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    end = layout.count() - 1
    if end >= 0 and layout.itemAt(end).spacerItem() is not None:
        layout.insertWidget(end, panel)
    else:
        layout.addWidget(panel)
    return page


__all__ = ["LiveWaveformPanel", "LiveWaveformPlot", "attach_live_waveform_panel"]
