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
        "liveWaveformPanel", "liveStreamSource",
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


def test_dedicated_live_page_replaces_measurement_card_embedding():
    text = (ROOT / "dpo4000_utils/gui_qt/composition/legacy_surface.py").read_text(
        encoding="utf-8"
    )
    assert "def _build_live_tab" in text
    assert "_composition_live_plot" in text
    assert "attach_live_waveform_panel(self, attach_measurement_trend_panel" not in text


def test_production_window_exposes_large_four_channel_live_view(monkeypatch):
    qt = pytest.importorskip("PySide6.QtWidgets")
    from dpo4000_utils.gui_qt.composition.window import QtScopeWindow

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = qt.QApplication.instance() or qt.QApplication([])
    window = QtScopeWindow()
    window.resize(1280, 760)
    window.show()
    window.page_controller.by_title["Live"].activate()
    app.processEvents()
    try:
        surface = window.feature_surface
        panel = window.findChild(qt.QWidget, "liveWaveformPanel")
        plot = window.findChild(qt.QWidget, "liveStreamPlot")
        assert panel is not None and plot is not None
        assert surface._composition_viewport_stack.currentWidget().objectName() == "liveWaveformViewport"
        assert plot.width() >= panel.width()
        for channel in range(1, 5):
            check = window.findChild(qt.QCheckBox, f"liveStreamSourceCH{channel}")
            assert check is not None and check.isChecked()
        window.page_controller.by_title["Measurement"].activate()
        app.processEvents()
        assert surface._composition_viewport_stack.currentWidget() is surface._composition_preview_view
    finally:
        window.close()
        app.processEvents()


def test_production_live_view_applies_and_collects_preferences(monkeypatch, tmp_path):
    qt = pytest.importorskip("PySide6.QtWidgets")
    from dpo4000_utils.gui.preferences import GuiPreferences, save_preferences
    from dpo4000_utils.gui_qt.composition.window import QtScopeWindow

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    path = tmp_path / "gui.json"
    save_preferences(GuiPreferences(
        live_sources="CH2,CH4",
        live_target_hz="10.0", live_render_points="5000",
    ), path)
    app = qt.QApplication.instance() or qt.QApplication([])
    window = QtScopeWindow(preferences_path=path)
    window.page_controller.by_title["Live"].activate()
    app.processEvents()
    try:
        panel = window.feature_surface._composition_live_stream_panel
        assert tuple(
            source for source, check in panel.channel_checks.items() if check.isChecked()
        ) == ("CH2", "CH4")
        assert panel.rate_combo.currentData() == 10.0
        assert panel.render_combo.currentData() == 5_000
        collected = window.feature_surface._collect_preferences()
        assert collected.live_sources == "CH2,CH4"
        assert not hasattr(panel, "points_combo")
    finally:
        window.close()
        app.processEvents()


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


def test_lease_gateway_admits_the_panels_own_action_name():
    """The host lease must admit exactly the description the panel submits."""
    panel = PANEL.read_text(encoding="utf-8")
    surface = (ROOT / "dpo4000_utils/gui_qt/composition/legacy_surface.py").read_text(
        encoding="utf-8"
    )
    assert "LIVE_ACTION_DESCRIPTION, execute," in panel
    assert ".startswith(LIVE_ACTION_DESCRIPTION)" in surface


def test_vertical_grid_auto_or_fixed_is_presentation_only(monkeypatch):
    qt = pytest.importorskip("PySide6.QtWidgets")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from dpo4000_utils.gui_qt.composition.pages.live_waveform import (
        LiveWaveformPanel, LiveWaveformPlot,
    )

    app = qt.QApplication.instance() or qt.QApplication([])
    plot = LiveWaveformPlot()
    frame = WaveformFrame.__new__(WaveformFrame)
    object.__setattr__(frame, "render_x", (0.0, 1.0))
    object.__setattr__(frame, "render_y", (0.2, 0.4))
    plot._frames = {"CH1": frame}
    auto = plot._bounds()
    assert auto is not None and auto[2] < 0.2 and auto[3] > 0.4
    plot.set_vertical_scale(0.5)
    assert plot._bounds() == (0.0, 1.0, -2.0, 2.0)
    plot.set_vertical_scale(None)
    assert plot._bounds() == auto
    for bad in (0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            plot.set_vertical_scale(bad)

    panel = LiveWaveformPanel(host=SimpleNamespace(), run_action=lambda *a, **k: None)
    panel.scale_combo.setCurrentIndex(panel.scale_combo.findData(2.0))
    assert panel.plot._volts_per_div == 2.0
    panel.scale_combo.setCurrentIndex(0)
    assert panel.plot._volts_per_div is None
    panel.shutdown()
    app.processEvents()


def _card_frame(source="CH1", label="", y_multiplier=0.01, n=100_000):
    from dpo4000_utils.waveform import WaveformData, WaveformPreamble

    preamble = WaveformPreamble(
        byte_width=2, encoding="BINARY", binary_format="RI", byte_order="MSB",
        record_point_count=n, point_format="Y", x_unit='"s"', x_increment=4e-8,
        x_zero=0.0, point_offset=0.0, y_unit='"V"', y_multiplier=y_multiplier,
        y_offset=0.0, y_zero=0.0,
    )
    wave = WaveformData(
        source=source, label=label, start_index=1, stop_index=n,
        requested_encoding="RIBINARY", preamble=preamble, samples=array("h", [0]) * n,
        acquired_at=datetime.now(timezone.utc),
    )
    return WaveformFrame(
        generation=1, sequence=1, acquired_monotonic_s=0.0,
        acquired_wall_time=datetime.now(timezone.utc), waveform=wave,
        acquisition_duration_s=0.1, render_x=(0.0, 1.0), render_y=(-1.2, 1.3),
    )


def test_channel_card_lines_are_brief_and_use_si_prefixes():
    pytest.importorskip("PySide6.QtWidgets")
    from dpo4000_utils.gui_qt.composition.pages.live_waveform import (
        channel_card_lines, format_si,
    )

    assert format_si(0.0012, "V") == "1.2 mV"
    assert format_si(25e6, "S/s") == "25 MS/s"
    assert format_si(4e-8, "s") == "40 ns"
    frame = _card_frame(y_multiplier=0.0003125)
    lines = channel_card_lines(frame)
    assert lines[0] == "Vert. res  312 µV/LSB"
    assert lines[1] == "Sample  40 ns (25 MS/s)"
    assert lines[2] == "Record  100,000 pts · 4 ms"
    assert lines[3] == "Horiz.  400 µs/div"
    assert lines[4] == "Vpp  2.5 V"
    assert len(lines) <= 5


def test_cards_follow_the_plot_and_show_only_displayed_channels(monkeypatch):
    qt = pytest.importorskip("PySide6.QtWidgets")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from dpo4000_utils.gui_qt.composition.pages.live_waveform import (
        LiveChannelCards, LiveWaveformPlot,
    )

    app = qt.QApplication.instance() or qt.QApplication([])
    plot, cards = LiveWaveformPlot(), LiveChannelCards()
    plot.attach_cards(cards)
    cards.show()
    assert cards.visible_sources == () and not cards._placeholder.isHidden()
    plot._cards.show_frames({"CH1": _card_frame("CH1", label="S11"),
                             "CH3": _card_frame("CH3")})
    assert cards.visible_sources == ("CH1", "CH3")
    assert "CH1 · S11" in cards.card_text("CH1") and "Vert. res" in cards.card_text("CH3")
    assert cards._placeholder.isHidden()
    plot._frames = {"CH1": _card_frame("CH1")}
    plot.mark_stale("Stopped")
    assert not cards._cards["CH1"].isEnabled()
    cards.show_frames({})
    assert cards.visible_sources == () and not cards._placeholder.isHidden()
    app.processEvents()
