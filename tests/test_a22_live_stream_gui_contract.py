"""GUI contracts and optional offscreen Qt runtime A22 tests."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from array import array

import pytest

from dpo4000_utils.live_stream import WaveformFrame

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "dpo4000_utils/gui_qt/composition/pages/live_waveform.py"


def test_stable_object_names_and_throttled_render_path():
    text = PANEL.read_text(encoding="utf-8")
    for name in (
        "liveWaveformPanel", "liveStreamSource", "liveStreamPoints",
        "liveStreamTargetRate", "liveStreamRenderPoints",
        "liveStreamStartButton", "liveStreamPauseButton",
        "liveStreamResumeButton", "liveStreamStopButton",
        "liveStreamPlot", "liveStreamStateLabel",
        "liveStreamStatsLabel", "liveStreamErrorLabel",
    ):
        assert name in text
    assert "setInterval(100)" in text
    assert "self.engine.begin_due()" in text
    assert "self.engine.take_latest()" in text


def test_attach_at_existing_measurement_page():
    text = (ROOT / "dpo4000_utils/gui_qt/composition/legacy_surface.py").read_text(
        encoding="utf-8"
    )
    assert "attach_live_waveform_panel(self, attach_measurement_trend_panel(self, page))" in text


def test_offscreen_panel_start_pause_resume_stop(monkeypatch):
    qt = pytest.importorskip("PySide6.QtWidgets")
    from dpo4000_utils.gui_qt.composition.pages.live_waveform import LiveWaveformPanel
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = qt.QApplication.instance() or qt.QApplication([])
    host = SimpleNamespace(
        _operation_active=False, _automation_any_active=lambda: False,
        _composition_live_lease=False,
    )
    queued = []

    def dispatch(description, execute, *, on_success, on_error, retain_session):
        assert retain_session
        queued.append((execute, on_success, on_error))

    panel = LiveWaveformPanel(host=host, run_action=dispatch)
    assert panel.objectName() == "liveWaveformPanel"
    panel.start()
    panel._cadence.stop()
    panel._acquire_if_due()
    assert len(queued) == 1
    assert panel.engine.in_flight
    assert host._composition_live_lease
    panel.pause()
    assert panel.engine.state.value == "PAUSED"
    panel.resume()
    assert panel.engine.state.value == "STARTING"
    # The stale completion must release the physical lease but change no state.
    _, callback, _ = queued.pop()
    stale = WaveformFrame(
        1, 1, 0, datetime.now(timezone.utc),
        SimpleNamespace(sample_count=4, samples=array("h", [0, 1, 2, 3])),
        0.01, (0., 1., 2., 3.), (0., 1., 2., 3.),
    )
    callback(stale)
    assert panel.engine.state.value == "STARTING"
    panel.stop()
    assert not host._composition_live_lease
    assert panel.engine.state.value == "IDLE"
    panel.shutdown()
    app.processEvents()
    panel.close()


def test_stop_keeps_shared_scope_lease_until_old_transfer_completes(monkeypatch):
    qt = pytest.importorskip("PySide6.QtWidgets")
    from dpo4000_utils.gui_qt.composition.pages.live_waveform import LiveWaveformPanel
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = qt.QApplication.instance() or qt.QApplication([])
    host = SimpleNamespace(
        _operation_active=False, _automation_any_active=lambda: False,
        _composition_live_lease=False,
    )
    pending = []

    def dispatch(description, execute, *, on_success, on_error, retain_session):
        pending.append(on_success)

    panel = LiveWaveformPanel(host=host, run_action=dispatch)
    panel.start()
    panel._cadence.stop()
    panel._acquire_if_due()
    assert panel.engine.in_flight
    panel.stop()
    assert host._composition_live_lease  # still inside the VISA worker
    assert panel.engine.state.value == "IDLE"
    pending.pop()(WaveformFrame(
        1, 1, 0, datetime.now(timezone.utc),
        SimpleNamespace(sample_count=4, samples=array("h", [0, 1, 2, 3])),
        0.01, (0., 1., 2., 3.), (0., 1., 2., 3.),
    ))
    assert not panel.engine.in_flight
    assert not host._composition_live_lease
    assert panel.engine.take_latest() is None
    panel.shutdown()
    app.processEvents()
    panel.close()


def test_synchronous_dispatch_failure_transitions_to_error(monkeypatch):
    qt = pytest.importorskip("PySide6.QtWidgets")
    from dpo4000_utils.gui_qt.composition.pages.live_waveform import LiveWaveformPanel
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = qt.QApplication.instance() or qt.QApplication([])
    host = SimpleNamespace(
        _operation_active=False, _automation_any_active=lambda: False,
        _composition_live_lease=False,
    )

    def dispatch(description, execute, *, on_success, on_error, retain_session):
        raise RuntimeError("scope worker unavailable")

    panel = LiveWaveformPanel(host=host, run_action=dispatch)
    panel.start()
    panel._cadence.stop()
    panel._acquire_if_due()
    assert panel.engine.state.value == "ERROR"
    assert panel.engine.stats().acquisition_errors == 1
    assert not panel.engine.in_flight
    assert not host._composition_live_lease
    assert "scope worker unavailable" in panel.error_label.text()
    panel.shutdown()
    app.processEvents()
    panel.close()
