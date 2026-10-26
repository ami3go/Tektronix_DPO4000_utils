"""10-second offscreen Qt heartbeat while A22 synthetic worker acquisition is active."""
from __future__ import annotations

import time
from array import array
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from dpo4000_utils.waveform import WaveformData, WaveformPreamble


def test_a22_synthetic_qt_heartbeat(monkeypatch):
    qtcore = pytest.importorskip("PySide6.QtCore")
    qtwidgets = pytest.importorskip("PySide6.QtWidgets")
    from dpo4000_utils.gui_qt.composition.pages.live_waveform import LiveWaveformPanel

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = qtwidgets.QApplication.instance() or qtwidgets.QApplication([])
    p = WaveformPreamble(
        byte_width=2, encoding="BINARY", binary_format="RI", byte_order="MSB",
        record_point_count=10000, point_format="Y", x_unit="s", x_increment=0.000001,
        x_zero=0.0, point_offset=0.0, y_unit="V", y_multiplier=0.01,
        y_offset=0.0, y_zero=0.0,
    )
    waveform = WaveformData(
        source="CH1", label="", start_index=1, stop_index=10000,
        requested_encoding="RIBINARY", preamble=p, samples=array("h", [10]) * 10000,
        acquired_at=datetime.now(timezone.utc),
    )

    class SlowFakeScope:
        def read_channel_waveform_data(self, channel, *, point_count):
            assert channel in (1, 2, 3, 4) and point_count == 10_000
            time.sleep(.03)
            return replace(waveform, source=f"CH{channel}")

    pool = ThreadPoolExecutor(max_workers=1)
    fake = SlowFakeScope()

    class Completer(qtcore.QObject):
        completed = qtcore.Signal(object)

        def __init__(self):
            super().__init__()
            self.completed.connect(
                self.deliver, qtcore.Qt.ConnectionType.QueuedConnection
            )

        @qtcore.Slot(object)
        def deliver(self, payload):
            success, failure, result, error = payload
            if error is None:
                success(result)
            else:
                failure(error)

    completer = Completer()
    host = SimpleNamespace(
        _operation_active=False, _automation_any_active=lambda: False,
        _composition_live_lease=False,
    )

    def dispatch(description, execute, *, on_success, on_error, retain_session):
        assert retain_session and description.startswith("A22")
        def run():
            try:
                answer = execute(fake)
                completer.completed.emit((on_success, on_error, answer, None))
            except BaseException as exc:
                completer.completed.emit((on_success, on_error, None, exc))
        pool.submit(run)

    panel = LiveWaveformPanel(
        host=host, run_action=dispatch,
        default_sources=("CH1", "CH2", "CH3", "CH4"),
    )
    panel.resize(900, 600)
    panel.show()  # exercise paintEvent, not only offscreen timers
    app.processEvents()
    panel.start()
    heartbeat = qtcore.QTimer()
    heartbeat.setInterval(50)
    ticks = []

    def beat():
        ticks.append(time.monotonic())

    heartbeat.timeout.connect(beat)
    heartbeat.start()
    loop = qtcore.QEventLoop()
    qtcore.QTimer.singleShot(10_200, loop.quit)
    try:
        loop.exec()
        assert len(ticks) >= 150
        gaps = [max(0.0, a - b - 0.05) for a, b in zip(ticks[1:], ticks[:-1])]
        ordered = sorted(gaps)
        p95 = ordered[int(0.95 * (len(ordered) - 1))]
        p99 = ordered[int(0.99 * (len(ordered) - 1))]
        print(
            f"A22 Qt heartbeat: count={len(gaps)}, p95={p95:.4f}s, "
            f"p99={p99:.4f}s, max={max(gaps):.4f}s"
        )
        assert p99 < 0.25
        assert max(gaps) < 1.0
        assert panel.engine.stats().frames_acquired > 2
        assert panel.engine.stats().channel_count == 4
    finally:
        heartbeat.stop()
        panel.shutdown()
        pool.shutdown(wait=True)
        app.processEvents()
        panel.close()
