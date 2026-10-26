"""Offline A22 regressions found on the DPO4054 bench; no scope, VISA or network.

``ScriptedScope`` answers the SCPI that the waveform driver issues and mimics
the DPO4000 behaviours that caused real field failures:

* a source that is not displayed never answers ``WFMOUTPRE:NR_PT?`` (error 2244),
  which only surfaces as a VISA timeout;
* ``DATA:STOP`` echoes the request while ``NR_PT`` is clamped to the record.

The window tests go through the production ``QtScopeWindow._run_action`` lease
gateway; the original lease bug was invisible to tests that bypassed it.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from dpo4000_utils.live_stream import MAX_POINTS, StreamConfig, StreamState, capture_group
from dpo4000_utils.waveform import DPOWaveformError, WaveformMixin


class ScriptedScope:
    def __init__(self, record_length: int = 100_000, displayed=(1,)):
        self.record_length = record_length
        self.displayed = set(displayed)
        self.source = "CH1"
        self.start = 1
        self.stop = record_length
        self.log: list[str] = []

    # -- SCPI surface used by dpo4000_utils.waveform --------------------------
    def write(self, command: str) -> None:
        self.log.append(command)
        name, _, value = command.partition(" ")
        if name == "DATA:SOURCE":
            self.source = value
        elif name == "DATA:START":
            self.start = int(value)
        elif name == "DATA:STOP":
            self.stop = int(value)  # the scope echoes the request, unclamped

    def _points(self) -> int:
        return min(self.stop, self.record_length) - self.start + 1

    def query(self, command: str) -> str:
        self.log.append(command)
        if command.startswith("SELECT:CH"):
            return "1" if int(command[9]) in self.displayed else "0"
        if command.startswith("WFMOUTPRE:") and int(self.source[2:]) not in self.displayed:
            raise TimeoutError("VI_ERROR_TMO: Timeout expired before operation completed.")
        table = {
            "DATA:START?": str(self.start), "DATA:STOP?": str(self.stop),
            "WFMOUTPRE:BYT_NR?": "2", "WFMOUTPRE:ENCDG?": "BIN",
            "WFMOUTPRE:BN_FMT?": "RI", "WFMOUTPRE:BYT_OR?": "MSB",
            "WFMOUTPRE:NR_PT?": str(self._points()), "WFMOUTPRE:PT_FMT?": "Y",
            "WFMOUTPRE:XUNIT?": "s", "WFMOUTPRE:XINCR?": "1.0E-6",
            "WFMOUTPRE:XZERO?": "0.0", "WFMOUTPRE:PT_OFF?": "0",
            "WFMOUTPRE:YUNIT?": "V", "WFMOUTPRE:YMULT?": "0.01",
            "WFMOUTPRE:YOFF?": "0.0", "WFMOUTPRE:YZERO?": "0.0",
        }
        if command in table:
            return table[command]
        if command.endswith(":LABEL?"):
            return '""'
        raise AssertionError(f"unscripted query {command!r}")

    def query_binary_values(self, command, *, container, data_points, **kwargs):
        self.log.append(command)
        return container([i % 100 for i in range(self._points())])

    def curve_reads(self) -> int:
        return self.log.count("CURVE?")


class Driver(WaveformMixin):
    """Just enough of the public driver: the mixin plus ensure_connected()."""

    def __init__(self, scope: ScriptedScope):
        self.scope = scope

    def ensure_connected(self):
        return self.scope


# --- driver / engine against the scripted scope ------------------------------
def test_requesting_more_points_than_the_record_reproduces_the_field_error():
    driver = Driver(ScriptedScope(record_length=100_000))
    with pytest.raises(DPOWaveformError, match="1000000 points.*NR_PT reports 100000"):
        driver.read_channel_waveform_data(1, point_count=1_000_000)


def test_scope_setup_read_uses_whatever_record_the_scope_has():
    for record in (1_000, 100_000):
        group = capture_group(Driver(ScriptedScope(record)), StreamConfig(), 1, 1)
        assert group.frames[0].waveform.sample_count == record


def test_size_cap_rejects_an_oversized_record_before_curve_is_issued():
    scope = ScriptedScope(record_length=MAX_POINTS + 1)
    with pytest.raises(DPOWaveformError, match="reduce the scope record length"):
        capture_group(Driver(scope), StreamConfig(), 1, 1)
    assert scope.curve_reads() == 0


def test_record_exactly_at_the_cap_is_accepted():
    scope = ScriptedScope(record_length=MAX_POINTS)
    group = capture_group(Driver(scope), StreamConfig(render_points=2_000), 1, 1)
    assert group.frames[0].waveform.sample_count == MAX_POINTS
    assert len(group.frames[0].render_y) <= 4_000


def test_hidden_channel_fails_fast_with_a_clear_message_and_no_transfer():
    scope = ScriptedScope(displayed=(1,))
    config = StreamConfig(sources=("CH1", "CH2", "CH3", "CH4"))
    with pytest.raises(ValueError, match="CH2, CH3, CH4 not displayed on the scope"):
        capture_group(Driver(scope), config, 1, 1)
    assert scope.curve_reads() == 0
    assert not any(c.startswith("DATA:SOURCE") for c in scope.log)


def test_without_the_precheck_a_hidden_channel_is_only_a_timeout():
    """Documents why the pre-check exists: the raw driver path just times out."""
    scope = ScriptedScope(displayed=(1,))
    with pytest.raises(Exception, match="(?i)timeout|timed out"):
        Driver(scope).read_channel_waveform_data(2)


def test_displayed_subset_streams_only_those_channels_and_never_writes_scope_state():
    scope = ScriptedScope(displayed=(1, 3))
    group = capture_group(Driver(scope), StreamConfig(sources=("CH1", "CH3")), 2, 5)
    assert [f.waveform.source for f in group.frames] == ["CH1", "CH3"]
    writes = {c.split(" ")[0] for c in scope.log if " " in c and not c.endswith("?")}
    assert writes <= {"DATA:SOURCE", "DATA:START", "DATA:STOP", "DATA:WIDTH", "DATA:ENCDG"}


# --- production window / lease gateway ---------------------------------------
@pytest.fixture
def window_env(monkeypatch, tmp_path):
    qtwidgets = pytest.importorskip("PySide6.QtWidgets")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from dpo4000_utils.gui.preferences import GuiPreferences, save_preferences
    from dpo4000_utils.gui_qt.composition.window import QtScopeWindow

    app = qtwidgets.QApplication.instance() or qtwidgets.QApplication([])
    made = []

    def build(prefs=None):
        path = tmp_path / "gui.json"
        save_preferences(prefs or GuiPreferences(), path)
        window = QtScopeWindow(preferences_path=path)
        made.append(window)
        window.page_controller.by_title["Live"].activate()
        app.processEvents()
        return window, window.feature_surface

    yield app, build
    for window in made:
        window.close()
    app.processEvents()


def _patch_base_dispatch(monkeypatch, surface, scope):
    """Replace the dispatch *behind* the lease gateway with a synchronous fake."""
    calls = []
    mro = type(surface).__mro__
    gateway = next(c for c in mro if "_run_action" in c.__dict__
                   and c.__module__.endswith("legacy_surface"))
    base = next(c for c in mro[mro.index(gateway) + 1:] if "_run_action" in c.__dict__)

    def fake(self, description, callback, *, on_success=None, on_error=None,
             retain_session=False):
        calls.append(description)
        try:
            result = callback(Driver(scope))
        except BaseException as exc:  # noqa: BLE001 - mirrors the worker contract
            if on_error:
                on_error(exc)
            return None
        if on_success:
            on_success(result)
        return None

    monkeypatch.setattr(base, "_run_action", fake)
    return calls


def _pump(app, predicate, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not predicate():
        app.processEvents()
        time.sleep(0.01)
    return predicate()


def test_lease_gateway_admits_live_reads_but_rejects_other_scope_actions(window_env, monkeypatch):
    app, build = window_env
    from dpo4000_utils.gui_qt.composition.pages.live_waveform import LIVE_ACTION_DESCRIPTION

    _window, surface = build()
    calls = _patch_base_dispatch(monkeypatch, surface, ScriptedScope())
    surface._composition_live_lease = True
    errors = []
    surface._run_action(LIVE_ACTION_DESCRIPTION, lambda scope: 1, on_error=errors.append)
    surface._run_action("Read measurements", lambda scope: 1, on_error=errors.append)
    assert calls == [LIVE_ACTION_DESCRIPTION]
    assert len(errors) == 1 and "A22 owns the instrument" in str(errors[0])
    surface._composition_live_lease = False
    surface._run_action("Read measurements", lambda scope: 1)
    assert calls[-1] == "Read measurements"


def test_start_streams_through_the_real_gateway_and_stop_releases_the_lease(window_env, monkeypatch):
    app, build = window_env
    _window, surface = build()
    _patch_base_dispatch(monkeypatch, surface, ScriptedScope(100_000, displayed=(1,)))
    panel = surface._composition_live_stream_panel
    for source in ("CH2", "CH3", "CH4"):
        panel.channel_checks[source].setChecked(False)
    panel.start()
    assert _pump(app, lambda: panel.engine.stats().frames_acquired >= 2)
    assert panel.engine.state is StreamState.RUNNING
    assert panel.error_label.text() == ""
    assert surface._composition_live_lease is True
    panel.stop()
    _pump(app, lambda: not surface._composition_live_lease)
    assert panel.engine.state is StreamState.IDLE and surface._composition_live_lease is False


def test_hidden_channel_selection_ends_in_a_readable_error_not_a_timeout(window_env, monkeypatch):
    app, build = window_env
    _window, surface = build()
    scope = ScriptedScope(displayed=(1,))
    _patch_base_dispatch(monkeypatch, surface, scope)
    shown = []
    monkeypatch.setattr(type(surface), "_message", lambda self, *a, **k: shown.append(a), raising=False)
    panel = surface._composition_live_stream_panel
    assert all(check.isChecked() for check in panel.channel_checks.values())
    panel.start()
    assert _pump(app, lambda: panel.engine.state is StreamState.ERROR)
    assert "CH2, CH3, CH4 not displayed" in (panel.error_label.text() or str(panel.engine.last_error))
    assert scope.curve_reads() == 0
    assert surface._composition_live_lease is False


def test_panel_has_no_transfer_size_selector(window_env):
    _app, build = window_env
    _window, surface = build()
    panel = surface._composition_live_stream_panel
    assert not hasattr(panel, "points_combo")
    assert panel._configuration().point_count is None


# --- vertical grid presentation / preferences --------------------------------
def test_vertical_grid_preference_round_trips_through_the_window(window_env):
    from dpo4000_utils.gui.preferences import GuiPreferences

    _app, build = window_env
    _window, surface = build(GuiPreferences(live_vertical_scale="2.0"))
    panel = surface._composition_live_stream_panel
    assert panel.scale_combo.currentData() == 2.0 and panel.plot._volts_per_div == 2.0
    assert surface._collect_preferences().live_vertical_scale == "2.0"
    panel.scale_combo.setCurrentIndex(0)
    assert panel.plot._volts_per_div is None
    assert surface._collect_preferences().live_vertical_scale == "auto"


def test_default_is_auto_and_legacy_point_count_preference_is_ignored(window_env, tmp_path):
    from dpo4000_utils.gui.preferences import load_preferences

    assert load_preferences(tmp_path / "missing.json").live_vertical_scale == "auto"
    legacy = tmp_path / "old.json"
    legacy.write_text('{"live_point_count": "1000000", "live_sources": "CH1"}', encoding="utf-8")
    loaded = load_preferences(legacy)
    assert loaded.live_sources == "CH1" and not hasattr(loaded, "live_point_count")
