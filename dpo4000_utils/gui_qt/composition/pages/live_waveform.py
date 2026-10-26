"""A22.1 grouped CH1..CH4 Live View using the serialized public-driver gateway."""
from __future__ import annotations

import math
from typing import Any, Callable

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ....live_stream import (
    LiveStreamEngine, StreamConfig, StreamState, WaveformFrame, WaveformGroup,
    capture_group,
)

CHANNEL_COLORS = {
    "CH1": QColor("#ffd21f"),
    "CH2": QColor("#35d8ff"),
    "CH3": QColor("#ff4fc8"),
    "CH4": QColor("#5ee36d"),
}


# Shared with the host lease gateway, which admits only this action while A22 is active.
LIVE_ACTION_DESCRIPTION = "A22 live waveform group"


class LiveWaveformPlot(QWidget):
    """Large, bounded, shared-axis CH1..CH4 waveform canvas."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("liveStreamPlot")
        self.setMinimumSize(640, 420)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._frames: dict[str, WaveformFrame] = {}
        self._sequence = 0
        self._skew_s = 0.0
        self._stale = False
        self._message = "Select Live, choose channels, then Start"

    @property
    def displayed_sources(self) -> tuple[str, ...]:
        return tuple(source for source in CHANNEL_COLORS if source in self._frames)

    def display(self, payload: WaveformFrame | WaveformGroup) -> None:
        if isinstance(payload, WaveformGroup):
            self._frames = {frame.waveform.source: frame for frame in payload.frames}
            self._sequence = payload.sequence
            self._skew_s = payload.channel_skew_s
        else:
            self._frames = {payload.waveform.source: payload}
            self._sequence = payload.sequence
            self._skew_s = 0.0
        self._stale = False
        self._message = ""
        self.update()

    def mark_stale(self, message: str = "Last complete group (stale)") -> None:
        self._stale = bool(self._frames)
        self._message = message
        self.update()

    def _bounds(self) -> tuple[float, float, float, float] | None:
        xs: list[float] = []
        ys: list[float] = []
        for frame in self._frames.values():
            if frame.render_x:
                xs.extend((frame.render_x[0], frame.render_x[-1]))
            ys.extend(value for value in frame.render_y if math.isfinite(value))
        if not xs or not ys or not all(math.isfinite(value) for value in xs):
            return None
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        if max_x <= min_x:
            return None
        if max_y <= min_y:
            padding = max(1e-9, abs(min_y) * 0.01)
            min_y -= padding
            max_y += padding
        else:
            padding = (max_y - min_y) * 0.05
            min_y -= padding
            max_y += padding
        return min_x, max_x, min_y, max_y

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), QColor("#071018"))
        box = QRectF(self.rect()).adjusted(64, 38, -22, -46)

        painter.setPen(QPen(QColor("#27404d"), 1, Qt.PenStyle.DotLine))
        for index in range(11):
            x = box.left() + index * box.width() / 10
            painter.drawLine(QPointF(x, box.top()), QPointF(x, box.bottom()))
        for index in range(9):
            y = box.top() + index * box.height() / 8
            painter.drawLine(QPointF(box.left(), y), QPointF(box.right(), y))
        painter.setPen(QPen(QColor("#6b8794"), 1))
        painter.drawRect(box)

        bounds = self._bounds()
        if bounds is None:
            painter.setPen(QColor("#b7c7d0"))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, self._message or "No complete waveform group")
            return
        min_x, max_x, min_y, max_y = bounds

        painter.save()
        painter.setClipRect(box)
        for source in CHANNEL_COLORS:
            frame = self._frames.get(source)
            if frame is None:
                continue
            path = QPainterPath()
            started = False
            for x_value, y_value in zip(frame.render_x, frame.render_y):
                if not (math.isfinite(x_value) and math.isfinite(y_value)):
                    started = False
                    continue
                point = QPointF(
                    box.left() + (x_value - min_x) * box.width() / (max_x - min_x),
                    box.bottom() - (y_value - min_y) * box.height() / (max_y - min_y),
                )
                if started:
                    path.lineTo(point)
                else:
                    path.moveTo(point)
                    started = True
            painter.setPen(QPen(CHANNEL_COLORS[source], 1.6))
            painter.drawPath(path)
        painter.restore()

        painter.setPen(QColor("#b7c7d0"))
        painter.drawText(6, int(box.top()) + 5, f"{max_y:.4g} V")
        painter.drawText(6, int(box.bottom()), f"{min_y:.4g} V")
        painter.drawText(
            int(box.left()), self.height() - 12,
            f"{min_x:.4g} .. {max_x:.4g} s   |   sequential group #{self._sequence}   |   skew {self._skew_s * 1000:.1f} ms",
        )
        legend_x = int(box.left())
        for source in self.displayed_sources:
            painter.setPen(QPen(CHANNEL_COLORS[source], 3))
            painter.drawLine(legend_x, 20, legend_x + 22, 20)
            painter.drawText(legend_x + 28, 25, source)
            legend_x += 78
        if self._stale:
            painter.setPen(QColor("#ffb347"))
            painter.drawText(box, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight, self._message)


class LiveWaveformPanel(QGroupBox):
    """Multi-channel controls with one in-flight complete acquisition group."""

    def __init__(
        self, *, host: Any, run_action: Callable[..., Any],
        plot: LiveWaveformPlot | None = None,
        show_plot: bool = True,
        default_sources: tuple[str, ...] = ("CH1",),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Live View (A22.1)", parent)
        self.setObjectName("liveWaveformPanel")
        self._host = host
        self._run_action = run_action
        self.plot = plot or LiveWaveformPlot(self)
        self._show_plot = show_plot
        self._default_sources = default_sources
        self.engine = LiveStreamEngine()
        self._closed = False
        self._restart_requested = False
        self._last_actual_points: dict[str, int] = {}
        self._transport = "not connected"
        self._cadence = QTimer(self)
        self._cadence.setSingleShot(True)
        self._cadence.timeout.connect(self._acquire_if_due)
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(100)
        self._render_timer.timeout.connect(self._refresh)
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Sequential CH1-CH4 record transfers published as one complete group. "
            "This is a live view, not lossless simultaneous ADC streaming."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        channel_row = QHBoxLayout()
        self.channel_checks: dict[str, QCheckBox] = {}
        for source in CHANNEL_COLORS:
            check = QCheckBox(source)
            check.setObjectName(f"liveStreamSource{source}")
            check.setChecked(source in self._default_sources)
            check.setStyleSheet(f"QCheckBox {{ color: {CHANNEL_COLORS[source].name()}; font-weight: 700; }}")
            check.toggled.connect(self._refresh_status)
            self.channel_checks[source] = check
            channel_row.addWidget(check)
        layout.addLayout(channel_row)

        form = QFormLayout()
        self.points_combo = QComboBox()
        self.points_combo.setObjectName("liveStreamPoints")
        for label, value in (("1k", 1_000), ("10k", 10_000),
                             ("100k", 100_000), ("1M", 1_000_000)):
            self.points_combo.addItem(label, value)
        self.points_combo.setCurrentIndex(1)
        self.points_combo.currentIndexChanged.connect(self._refresh_status)
        form.addRow("Per channel", self.points_combo)
        self.rate_combo = QComboBox()
        self.rate_combo.setObjectName("liveStreamTargetRate")
        for hz in (1, 2, 5, 10, 20, 100):
            self.rate_combo.addItem("Maximum" if hz == 100 else f"{hz} groups/s", float(hz))
        self.rate_combo.setCurrentIndex(2)
        self.rate_combo.currentIndexChanged.connect(self._refresh_status)
        form.addRow("Requested group rate", self.rate_combo)
        self.render_combo = QComboBox()
        self.render_combo.setObjectName("liveStreamRenderPoints")
        for count in (500, 1_000, 2_000, 5_000, 10_000):
            self.render_combo.addItem(f"{count:,}", count)
        self.render_combo.setCurrentIndex(2)
        self.render_combo.currentIndexChanged.connect(self._refresh_status)
        form.addRow("Render points/channel", self.render_combo)
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
        self.restart_button = QPushButton("Restart")
        self.restart_button.setObjectName("liveStreamRestartButton")
        for button, callback in (
            (self.start_button, self.start), (self.pause_button, self.pause),
            (self.resume_button, self.resume), (self.stop_button, self.stop),
            (self.restart_button, self.restart),
        ):
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)

        if self._show_plot:
            layout.addWidget(self.plot, 1)
        self.state_label = QLabel()
        self.state_label.setObjectName("liveStreamStateLabel")
        self.stats_label = QLabel()
        self.stats_label.setObjectName("liveStreamStatsLabel")
        self.stats_label.setWordWrap(True)
        self.error_label = QLabel()
        self.error_label.setObjectName("liveStreamErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #ffb347;")
        layout.addWidget(self.state_label)
        layout.addWidget(self.stats_label)
        layout.addWidget(self.error_label)
        layout.addStretch(1)

    def _configuration(self) -> StreamConfig:
        sources = tuple(
            source for source, check in self.channel_checks.items() if check.isChecked()
        )
        return StreamConfig(
            sources=sources,
            point_count=self.points_combo.currentData(),
            target_hz=float(self.rate_combo.currentData()),
            render_points=int(self.render_combo.currentData()),
        )

    def _sync_lease(self) -> None:
        self._host._composition_live_lease = (
            self.engine.in_flight
            or self.engine.state not in {StreamState.IDLE, StreamState.ERROR}
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
        selected_resource = getattr(self._host, "_selected_resource", None)
        if callable(selected_resource):
            try:
                self._transport = str(selected_resource())
            except Exception:  # validation is repeated by the dispatch boundary
                self._transport = "unresolved"
        self._last_actual_points = {}
        self.error_label.clear()
        self._sync_lease()
        self._render_timer.start()
        self._schedule()
        self._refresh()

    def pause(self) -> None:
        if self.engine.state not in {StreamState.STARTING, StreamState.RUNNING}:
            return
        self.engine.pause()
        self._cadence.stop()
        self.plot.mark_stale("Paused — last complete group")
        self._refresh()

    def resume(self) -> None:
        if self.engine.state is not StreamState.PAUSED:
            return
        self.engine.resume()
        self.error_label.clear()
        self._schedule()
        self._refresh()

    def _stop(self, *, preserve_restart: bool) -> None:
        self._cadence.stop()
        self._render_timer.stop()
        if not preserve_restart:
            self._restart_requested = False
        self.engine.stop()
        self._sync_lease()
        self.plot.mark_stale("Stopped — last complete group")
        self._refresh()

    def stop(self) -> None:
        self._stop(preserve_restart=False)

    def restart(self) -> None:
        self._restart_requested = True
        self._stop(preserve_restart=True)
        self._start_requested_restart_when_released()

    def _start_requested_restart_when_released(self) -> None:
        if not self._restart_requested or self.engine.in_flight or self._closed:
            return
        self._restart_requested = False
        QTimer.singleShot(0, self.start)

    def shutdown(self) -> None:
        self._closed = True
        self._restart_requested = False
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

        def execute(scope: Any) -> WaveformGroup:
            return capture_group(scope, config, token[0], token[1])

        def success(result: Any) -> None:
            if not isinstance(result, (WaveformFrame, WaveformGroup)):
                self.engine.fail(token, TypeError("Driver returned invalid waveform group"))
            elif self.engine.complete(token, result):
                if isinstance(result, WaveformGroup):
                    self._last_actual_points = {
                        frame.waveform.source: frame.waveform.sample_count
                        for frame in result.frames
                    }
                else:
                    self._last_actual_points = {
                        result.waveform.source: result.waveform.sample_count
                    }
            self._sync_lease()
            self._start_requested_restart_when_released()
            if not self._closed:
                self._schedule()
                self._refresh_status()

        def failure(exc: BaseException) -> None:
            self.engine.fail(token, exc)
            self._sync_lease()
            self._start_requested_restart_when_released()
            self.plot.mark_stale("Acquisition failed — last complete group")
            if not self._closed:
                self._schedule()
                self._refresh_status()

        try:
            self._run_action(
                LIVE_ACTION_DESCRIPTION, execute,
                on_success=success, on_error=failure, retain_session=True,
            )
        except Exception as exc:
            failure(exc)

    def _refresh(self) -> None:
        payload = self.engine.take_latest()
        if payload is not None and self.engine.state is StreamState.RUNNING:
            self.plot.display(payload)
        self._refresh_status()

    def _refresh_status(self) -> None:
        state = self.engine.state
        idle = state in {StreamState.IDLE, StreamState.ERROR}
        selected_sources = tuple(
            source for source, check in self.channel_checks.items() if check.isChecked()
        )
        visible_sources = selected_sources if idle else (self.engine.config.sources or ())
        sources = ",".join(visible_sources) or "no channels selected"
        requested_rate = (
            float(self.rate_combo.currentData()) if idle else self.engine.config.target_hz
        )
        self.state_label.setText(
            f"State: {state.value} | {sources} | requested {requested_rate:g} groups/s"
        )
        self.start_button.setEnabled(idle and not self._closed)
        self.pause_button.setEnabled(state in {StreamState.STARTING, StreamState.RUNNING})
        self.resume_button.setEnabled(state is StreamState.PAUSED)
        self.stop_button.setEnabled(state is not StreamState.IDLE)
        self.restart_button.setEnabled(not self._closed)
        for control in (*self.channel_checks.values(), self.points_combo, self.rate_combo, self.render_combo):
            control.setEnabled(idle)
        stats = self.engine.stats()
        durations = " ".join(
            f"{source} {duration * 1000:.0f}ms"
            for source, duration in stats.latest_channel_durations_s
        ) or "waiting"
        point_text = ", ".join(
            f"{source}:{count:,}" for source, count in self._last_actual_points.items()
        ) or f"requested {int(self.points_combo.currentData()):,}/channel"
        displayed_channel_count = len(visible_sources) if idle else stats.channel_count
        self.stats_label.setText(
            f"Actual {stats.acquisition_fps:.2f} groups/s | render {stats.render_fps:.2f}/s | "
            f"channels {displayed_channel_count} | {point_text} | cycle {stats.latest_acquisition_s * 1000:.1f} ms | "
            f"skew {stats.latest_channel_skew_s * 1000:.1f} ms | {durations} | "
            f"p50/p95/p99 {stats.p50_acquisition_s * 1000:.0f}/"
            f"{stats.p95_acquisition_s * 1000:.0f}/{stats.p99_acquisition_s * 1000:.0f} ms | "
            f"{stats.transfer_bytes_per_s / 1e6:.2f} MB/s | complete {stats.frames_acquired} | "
            f"rendered {stats.frames_rendered} | replaced {stats.frames_replaced} | "
            f"skipped {stats.deadlines_skipped} | errors {stats.acquisition_errors} | "
            f"transport {self._transport}"
        )
        if stats.last_error:
            self.error_label.setText(stats.last_error)


def attach_live_waveform_panel(host: Any, page: QWidget) -> QWidget:
    """Legacy compatibility helper; production A22.1 uses the dedicated Live page."""
    body = page.widget() if isinstance(page, QScrollArea) else page
    layout = body.layout()
    if layout is None:
        layout = QVBoxLayout(body)
    panel = LiveWaveformPanel(host=host, run_action=host._run_action, parent=body)
    host._composition_live_stream_panel = panel
    layout.addWidget(panel)
    return page


__all__ = [
    "CHANNEL_COLORS", "LiveWaveformPanel", "LiveWaveformPlot",
    "attach_live_waveform_panel",
]
