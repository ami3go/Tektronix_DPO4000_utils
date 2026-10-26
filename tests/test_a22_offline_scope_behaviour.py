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
        self.vscale = {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0}  # V/div; drives YMULT
        self.hscale = "200.0E-6"
        # None -> a realistic combined reply; a string overrides it (e.g. garbage).
        self.combined_reply: str | None = None

    def combined(self) -> str:
        """Headerless WFMOUTPRE? as the DPO4054 sends it, extras included."""
        return (
            f'2;16;BIN;RI;MSB;"{self.source.title()}, DC coupling, 1.000V/div, '
            f'200.0us/div, {self._points()} points, Hi Res mode";{self._points()};Y;LINEA;'
            f'"s";1.0E-6;-9.0E-4;0;"V";{self._ymult()};0.0E+0;0.0E+0;TIM;ANALOG;0.0E+0;0.0E+0;0.0E+0'
        )

    def _ymult(self) -> str:
        return repr(0.01 * self.vscale[int(self.source[2:])])

    def setting_queries(self) -> list[str]:
        return [c for c in self.log if c.startswith(("HOR:", "ACQ:")) or (
            c.startswith("CH") and c.split(":")[-1] in ("SCALE?", "POSITION?", "OFFSET?"))]

    def preamble_queries(self) -> list[str]:
        return [c for c in self.log if c.startswith("WFMOUTPRE")]

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
        if command.startswith("HOR:SCALE"):
            return self.hscale
        if command in ("HOR:RECORDLENGTH?", "HOR:DELAY:TIME?", "ACQ:MODE?"):
            return {"HOR:RECORDLENGTH?": str(self.record_length),
                    "HOR:DELAY:TIME?": "0.0E+0", "ACQ:MODE?": "HIR"}[command]
        if command.startswith("CH") and command.split(":")[1] in ("SCALE?", "POSITION?", "OFFSET?"):
            channel = int(command[2])
            return {"SCALE?": repr(self.vscale[channel]), "POSITION?": "0.0",
                    "OFFSET?": "0.0"}[command.split(":")[1]]
        if command.startswith("SELECT:CH"):
            return "1" if int(command[9]) in self.displayed else "0"
        if command.startswith("WFMOUTPRE") and int(self.source[2:]) not in self.displayed:
            raise TimeoutError("VI_ERROR_TMO: Timeout expired before operation completed.")
        if command == "WFMOUTPRE?":
            return self.combined() if self.combined_reply is None else self.combined_reply
        table = {
            "DATA:START?": str(self.start), "DATA:STOP?": str(self.stop),
            "WFMOUTPRE:BYT_NR?": "2", "WFMOUTPRE:ENCDG?": "BIN",
            "WFMOUTPRE:BN_FMT?": "RI", "WFMOUTPRE:BYT_OR?": "MSB",
            "WFMOUTPRE:NR_PT?": str(self._points()), "WFMOUTPRE:PT_FMT?": "Y",
            "WFMOUTPRE:XUNIT?": "s", "WFMOUTPRE:XINCR?": "1.0E-6",
            "WFMOUTPRE:XZERO?": "-9.0E-4", "WFMOUTPRE:PT_OFF?": "0",
            "WFMOUTPRE:YUNIT?": "V", "WFMOUTPRE:YMULT?": self._ymult(),
            "WFMOUTPRE:YOFF?": "0.0", "WFMOUTPRE:YZERO?": "0.0",
        }
        if command in table:
            return table[command]
        if command.endswith(":LABEL?"):
            return '""'
        raise AssertionError(f"unscripted query {command!r}")

    def query_binary_values(self, command, *, container, data_points, **kwargs):
        self.log.append(command)
        values = [i % 100 for i in range(self._points())]
        if kwargs.get("datatype") == "B":  # raw block: big-endian int16, as the scope sends it
            assert container is bytes and data_points == 2 * len(values)
            return b"".join(v.to_bytes(2, "big", signed=True) for v in values)
        return container(values)

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


# --- single-query preamble (WFMOUTPRE?) --------------------------------------
def test_one_combined_preamble_query_replaces_the_nine_field_queries():
    scope = ScriptedScope(record_length=10_000)
    wave = Driver(scope).read_channel_waveform_data(1)
    assert scope.preamble_queries() == ["WFMOUTPRE?"]
    assert wave.sample_count == 10_000


def test_combined_and_per_field_preambles_are_identical():
    fast = ScriptedScope()
    slow = ScriptedScope()
    slow.combined_reply = "garbage"  # forces the per-field fallback
    a = Driver(fast).read_channel_waveform_data(1).preamble
    b = Driver(slow).read_channel_waveform_data(1).preamble
    assert a == b
    assert len(slow.preamble_queries()) > 9 and len(fast.preamble_queries()) == 1


@pytest.mark.parametrize("reply", [
    "",                                                      # empty
    "garbage",
    ":WFMOUTPRE:BYT_NR 2;BIT_NR 16;ENCDG BIN",               # HEADER ON
    "2;16;BIN;RI;MSB",                                       # truncated
    '2;16;BIN;RI;MSB;"wfid";100;Y;LINEA;"s";abc;0;0;"V";1;0;0',  # non-numeric
    '2;16;BIN;RI;MSB;"wfid";100;Y;LINEA;"s";nan;0;0;"V";1;0;0',  # non-finite
    '2;16;BIN;RI;MSB;"wfid";100;Y;LINEA;s;1;0;0;V;1;0;0',    # unquoted units: no anchor
])
def test_untrustworthy_combined_reply_falls_back_to_per_field_queries(reply):
    scope = ScriptedScope()
    scope.combined_reply = reply
    wave = Driver(scope).read_channel_waveform_data(1)
    assert wave.sample_count == 100_000 and wave.preamble.x_increment == 1e-6
    assert len(scope.preamble_queries()) > 9


def test_combined_preamble_tolerates_extra_firmware_fields_and_quoted_semicolons():
    from dpo4000_utils.waveform import _parse_combined_preamble

    reply = ('2;16;BIN;RI;MSB;"Ch1; odd, label";500;Y;LINEA;"s";2.0E-9;-1.0E-6;0;"V";'
             '0.5;-2.0E+1;0.1;TIM;ANALOG;0;0;0;EXTRA;MORE')
    pre = _parse_combined_preamble(reply)
    assert pre is not None
    assert (pre.record_point_count, pre.x_unit, pre.y_unit) == (500, "s", "V")
    assert (pre.x_increment, pre.x_zero, pre.y_multiplier, pre.y_offset, pre.y_zero) == (
        2e-9, -1e-6, 0.5, -20.0, 0.1)


def test_hidden_channel_timeout_on_the_combined_query_still_propagates():
    scope = ScriptedScope(displayed=(1,))
    with pytest.raises(Exception, match="(?i)timeout|timed out"):
        Driver(scope).read_channel_waveform_data(2)


def test_a_group_cycle_issues_one_preamble_query_per_channel():
    scope = ScriptedScope(displayed=(1, 2, 3, 4))
    capture_group(Driver(scope), StreamConfig(sources=("CH1", "CH2", "CH3", "CH4")), 1, 1)
    assert scope.preamble_queries() == ["WFMOUTPRE?"] * 4


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


# --- preamble cache + raw-bytes decode (live streaming fast path) -------------
def _cycle(scope, cache, sources=("CH1", "CH2", "CH3", "CH4")):
    return capture_group(Driver(scope), StreamConfig(sources=sources), 1, 1, preamble_cache=cache)


def test_cache_reuses_the_preamble_while_the_setup_is_unchanged():
    from dpo4000_utils.waveform import PreambleCache

    scope, cache = ScriptedScope(displayed=(1, 2, 3, 4)), PreambleCache()
    _cycle(scope, cache)
    assert scope.preamble_queries() == ["WFMOUTPRE?"] * 4 and cache.misses == 4
    scope.log.clear()
    group = _cycle(scope, cache)
    assert scope.preamble_queries() == [] and cache.hits == 4
    assert [f.waveform.sample_count for f in group.frames] == [100_000] * 4
    # the horizontal fingerprint is read once per cycle, not once per channel
    assert scope.setting_queries().count("HOR:SCALE?") == 1


def test_cache_notices_a_vertical_change_on_only_that_channel_and_scales_correctly():
    from dpo4000_utils.waveform import PreambleCache

    scope, cache = ScriptedScope(displayed=(1, 2, 3, 4)), PreambleCache()
    first = _cycle(scope, cache)
    scope.vscale[3] = 2.0
    scope.log.clear()
    second = _cycle(scope, cache)
    assert scope.preamble_queries() == ["WFMOUTPRE?"]  # CH3 only
    ymult = {f.waveform.source: f.waveform.preamble.y_multiplier for f in second.frames}
    assert ymult == {"CH1": 0.01, "CH2": 0.01, "CH3": 0.02, "CH4": 0.01}
    assert first.frames[2].waveform.preamble.y_multiplier == 0.01


@pytest.mark.parametrize("change", ["hscale", "record"])
def test_cache_refreshes_every_channel_when_the_horizontal_setup_changes(change):
    from dpo4000_utils.waveform import PreambleCache

    scope, cache = ScriptedScope(displayed=(1, 2, 3, 4)), PreambleCache()
    _cycle(scope, cache)
    if change == "hscale":
        scope.hscale = "400.0E-6"
    else:
        scope.record_length = 50_000
        scope.stop = 50_000
    scope.log.clear()
    group = _cycle(scope, cache)
    assert scope.preamble_queries() == ["WFMOUTPRE?"] * 4
    if change == "record":
        assert group.frames[0].waveform.sample_count == 50_000


def test_cache_entries_expire_after_max_age_even_if_the_fingerprint_is_unchanged():
    from dpo4000_utils.waveform import PreambleCache

    now = [0.0]
    scope, cache = ScriptedScope(), PreambleCache(max_age_s=5.0, clock=lambda: now[0])
    _cycle(scope, cache, ("CH1",))
    now[0] = 4.9
    scope.log.clear(); _cycle(scope, cache, ("CH1",))
    assert scope.preamble_queries() == []
    now[0] = 5.1
    _cycle(scope, cache, ("CH1",))
    assert scope.preamble_queries() == ["WFMOUTPRE?"]


def test_cache_is_keyed_by_the_request_and_ignores_non_channel_sources():
    from dpo4000_utils.waveform import PreambleCache

    scope, cache = ScriptedScope(), PreambleCache()
    driver = Driver(scope)
    driver.read_channel_waveform_data(1, point_count=1_000, preamble_cache=cache)
    scope.log.clear()
    driver.read_channel_waveform_data(1, point_count=2_000, preamble_cache=cache)
    assert scope.preamble_queries() == ["WFMOUTPRE?"]  # different range -> not reused
    calls = []
    cache.get_or_read(scope, "MATH", (1, None, 2, "RIBINARY"), lambda s: calls.append(1) or "p")
    cache.get_or_read(scope, "MATH", (1, None, 2, "RIBINARY"), lambda s: calls.append(1) or "p")
    assert calls == [1, 1]


def test_fast_raw_bytes_decode_matches_the_standard_path_sample_for_sample():
    from dpo4000_utils.waveform import PreambleCache

    scope = ScriptedScope(record_length=5_000)
    standard = Driver(scope).read_channel_waveform_data(1)
    fast = Driver(scope).read_channel_waveform_data(1, preamble_cache=PreambleCache())
    assert list(fast.samples) == list(standard.samples) and fast.preamble == standard.preamble
    assert fast.samples.typecode == standard.samples.typecode == "h"


def test_fast_path_rejects_a_short_or_misaligned_block_with_a_driver_error():
    from dpo4000_utils.waveform import PreambleCache

    scope = ScriptedScope(record_length=1_000)
    scope.query_binary_values = lambda *a, **k: b"\x00" * 1_999  # odd byte count
    with pytest.raises(DPOWaveformError):
        Driver(scope).read_channel_waveform_data(1, preamble_cache=PreambleCache())
    scope.query_binary_values = lambda *a, **k: [1, 2, 3]  # not bytes
    with pytest.raises(DPOWaveformError, match="not bytes"):
        Driver(scope).read_channel_waveform_data(1, preamble_cache=PreambleCache())


def test_hidden_channel_still_fails_fast_with_the_cache_enabled():
    from dpo4000_utils.waveform import PreambleCache

    scope = ScriptedScope(displayed=(1,))
    with pytest.raises(ValueError, match="CH2 not displayed"):
        _cycle(scope, PreambleCache(), ("CH1", "CH2"))
    assert scope.curve_reads() == 0


def test_every_start_gets_a_fresh_cache(window_env, monkeypatch):
    app, build = window_env
    _window, surface = build()
    _patch_base_dispatch(monkeypatch, surface, ScriptedScope(displayed=(1,)))
    panel = surface._composition_live_stream_panel
    for source in ("CH2", "CH3", "CH4"):
        panel.channel_checks[source].setChecked(False)
    caches = []
    for _ in range(2):
        panel.start()
        assert _pump(app, lambda: panel.engine.stats().frames_acquired >= 2)
        caches.append(panel._preamble_cache)
        assert caches[-1].hits >= 1 and caches[-1].misses == 1
        panel.stop()
        _pump(app, lambda: not surface._composition_live_lease)
    assert caches[0] is not caches[1]
