"""Offline tests for scripts/run_live_view_soak.py (no scope, VISA, GUI or network).

A simulated clock advances only through ``sleep`` and the fake scope's reads, so a
full 12 h soak runs in seconds and is fully deterministic.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from test_a22_offline_scope_behaviour import Driver, ScriptedScope

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
_spec = importlib.util.spec_from_file_location("run_live_view_soak", SCRIPTS / "run_live_view_soak.py")
soak = importlib.util.module_from_spec(_spec)
sys.modules["run_live_view_soak"] = soak
_spec.loader.exec_module(soak)

IDN = "TEKTRONIX,DPO4054,C011280,CF:91.1CT FV:v2.68"


class SimClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(0.0, seconds)


class SoakScope(Driver):
    """Driver-shaped fake: advances the simulated clock like real transfers do."""

    def __init__(self, clock, *, record_length=1_000, displayed=(1, 2, 3, 4), read_s=0.08, hook=None):
        self.scope = ScriptedScope(record_length=record_length, displayed=displayed)
        self.clock, self.read_s, self.hook = clock, read_s, hook
        self.reads = 0
        self.extra = "A"
        self.scope_wrap()

    def scope_wrap(self):
        inner = self.scope
        outer = self
        original_query, original_binary = inner.query, inner.query_binary_values
        inner.width, inner.encdg = "2", "RIBINARY"
        original_write = inner.write

        def write(command):
            if command.startswith("DATA:WIDTH "):
                inner.width = command.split()[1]
            if command.startswith("DATA:ENCDG "):
                inner.encdg = command.split()[1]
            original_write(command)

        def query(command):
            if command == "SET?":
                return (f"EXTRA {outer.extra};HOR:SCALE {inner.hscale};"
                        + ";".join(f"CH{n}:SCALE {v}" for n, v in inner.vscale.items()))
            if command == "DATA:SOURCE?":
                return inner.source
            if command == "DATA:WIDTH?":
                return inner.width
            if command == "DATA:ENCDG?":
                return inner.encdg
            return original_query(command)

        def binary(command, **kwargs):
            outer.reads += 1
            outer.clock.now += outer.read_s
            if outer.hook:
                outer.hook(outer)
            return original_binary(command, **kwargs)

        inner.write, inner.query, inner.query_binary_values = write, query, binary

    def query_identity(self):
        return IDN

    def disconnect(self):
        pass


@pytest.fixture(autouse=True)
def _isolated_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(soak.base, "_lock_path", lambda resource: tmp_path / "soak.lock")


def _args(tmp_path, *extra):
    return soak.parse_args([
        "--resource", "SIM::INSTR", "--output-dir", str(tmp_path / "out"),
        "--sample-seconds", "30", "--checkpoint-seconds", "600", *extra,
    ])


def _run(tmp_path, *extra, scopes=None, **scope_kw):
    clock = SimClock()
    args = _args(tmp_path, *extra)
    made = []

    def connect(resource, timeout_ms):
        scope = (scopes.pop(0)(clock) if scopes else SoakScope(clock, **scope_kw))
        made.append(scope)
        return scope

    code = soak.run_soak(args, connect, clock=clock, sleep=clock.sleep)
    report = json.loads((tmp_path / "out" / "live_soak_report.json").read_text(encoding="utf-8"))
    return code, report, made


def test_full_12h_soak_passes_and_validates(tmp_path, monkeypatch):
    monkeypatch.setattr(soak, "POLL_S", 0.5)  # coarser polling keeps the simulation fast
    code, report, made = _run(tmp_path, "--duration-hours", "12", "--target-hz", "0.2",
                              "--lifecycle-minutes", "30", record_length=100)
    s = report["summary"]
    assert code == 0 and s["status"] == "PASS" and s["run_state"] == "FINAL", s["failure_reasons"]
    assert s["qualifying_duration_met"] is True and s["elapsed_s"] >= 12 * 3600
    assert s["groups_completed"] > 8_000 and s["group_failures"] == 0
    assert s["lifecycle_ops"] >= 20  # every 30 min over 12 h: pause/resume + stop/restart
    assert s["data_registers_restored"] is True and s["set_unchanged"] is True
    assert s["sources"] == ["CH1", "CH2", "CH3", "CH4"]
    assert 0.3 < s["group_latency_p50_s"] < 1.0 and s["skew_max_s"] > 0
    assert len(report["samples"]) >= 12 * 3600 // 30 - 5
    assert soak.validate_report(tmp_path / "out", min_hours=12, expected_commit=None) == []
    assert (tmp_path / "out" / "set_before.txt").is_file() and (tmp_path / "out" / "set_after.txt").is_file()
    assert len(made) == 1


def test_short_run_is_reported_as_not_qualifying_and_fails_validation(tmp_path):
    code, report, _ = _run(tmp_path, "--duration-hours", "0.05", "--target-hz", "1")
    assert code == 0 and report["summary"]["qualifying_duration_met"] is False
    problems = soak.validate_report(tmp_path / "out", min_hours=12, expected_commit=None)
    assert any("< required 12" in p for p in problems)
    assert soak.validate_report(tmp_path / "out", min_hours=0.04, expected_commit=None) == []
    assert any("commit" in p for p in soak.validate_report(
        tmp_path / "out", min_hours=0.04, expected_commit="f" * 40))


def test_group_failure_reconnects_and_stays_within_the_failure_budget(tmp_path):
    state = {"first": True}

    def flaky(clock):
        scope = SoakScope(clock)
        if state["first"]:
            state["first"] = False

            def boom(outer):
                if outer.reads == 6:
                    raise TimeoutError("VI_ERROR_TMO: Timeout expired")
            scope.hook = boom
        return scope

    code, report, made = _run(tmp_path, "--duration-hours", "0.2", "--target-hz", "1",
                              scopes=[flaky, SoakScope, SoakScope, SoakScope])
    s = report["summary"]
    assert code == 0 and s["status"] == "PASS", s["failure_reasons"]
    assert s["group_failures"] == 1 and s["reconnects"] == 1 and len(made) >= 2
    assert "Timeout" in report["failures"][0]["error_type"]
    assert s["groups_completed"] > 50


def test_too_many_failures_fail_the_soak(tmp_path):
    def always_fail(clock):
        scope = SoakScope(clock)

        def boom(outer):
            raise TimeoutError("VI_ERROR_TMO")
        scope.hook = boom
        return scope

    code, report, _ = _run(tmp_path, "--duration-hours", "0.5", "--target-hz", "1",
                           "--max-failures", "2", scopes=[always_fail] * 60)
    s = report["summary"]
    assert code == 1 and s["status"] == "FAIL"
    assert any("exceeded maximum 2" in r for r in s["failure_reasons"])


def test_hidden_channel_is_a_preflight_failure_with_no_streaming(tmp_path):
    code, report, _ = _run(tmp_path, "--duration-hours", "0.1", displayed=(1,))
    s = report["summary"]
    assert code == 1 and s["groups_completed"] == 0
    assert any("CH2, CH3, CH4 not displayed" in r for r in s["failure_reasons"])


def test_selecting_a_subset_streams_only_those_channels(tmp_path):
    code, report, _ = _run(tmp_path, "--duration-hours", "0.1", "--sources", "CH1,CH3",
                           "--target-hz", "1", displayed=(1, 3))
    assert code == 0 and report["summary"]["sources"] == ["CH1", "CH3"]


def test_setup_change_during_the_soak_is_detected_as_drift(tmp_path):
    def drift(outer):
        if outer.reads == 40:
            outer.scope.vscale[2] = 2.0

    code, report, _ = _run(tmp_path, "--duration-hours", "0.3", "--target-hz", "1",
                           hook=drift)
    s = report["summary"]
    assert code == 1 and any("setup drifted" in r for r in s["failure_reasons"])


def test_full_setup_difference_at_the_end_fails_even_if_the_stream_was_unaffected(tmp_path):
    def front_panel(outer):
        if outer.reads == 40:
            outer.extra = "B"  # a setting the waveform path never touches

    code, report, _ = _run(tmp_path, "--duration-hours", "0.3", "--target-hz", "1", hook=front_panel)
    s = report["summary"]
    assert code == 1 and s["set_unchanged"] is False
    assert s["set_diff"] == ["EXTRA A -> EXTRA B"]
    assert s["data_registers_restored"] is True


def test_group_latency_limit_stops_a_stalling_run(tmp_path):
    code, report, _ = _run(tmp_path, "--duration-hours", "0.5", "--target-hz", "1",
                           "--max-group-latency-s", "1.0", read_s=2.0)
    assert code == 1 and any("exceeded 1s" in r for r in report["summary"]["failure_reasons"])


def test_progressive_latency_degradation_is_detected(tmp_path):
    def slower(outer):
        outer.read_s = 0.08 + outer.reads * 0.0004  # grows steadily

    code, report, _ = _run(tmp_path, "--duration-hours", "2", "--target-hz", "0.5",
                           "--max-group-latency-s", "600", hook=slower)
    assert code == 1
    assert any("progressively degraded" in r for r in report["summary"]["failure_reasons"])


def test_a_second_soak_on_the_same_resource_is_blocked(tmp_path):
    soak.base._acquire_lock("SIM::INSTR")
    try:
        code = soak.run_soak(_args(tmp_path, "--duration-hours", "0.1"), lambda *a: None)
    finally:
        soak.base._lock_path("SIM::INSTR").unlink(missing_ok=True)
    assert code == 1


def test_lock_is_released_after_a_run(tmp_path):
    _run(tmp_path, "--duration-hours", "0.05", "--target-hz", "1")
    assert not soak.base._lock_path("SIM::INSTR").exists()


def test_checkpoints_write_a_running_report_before_the_end(tmp_path):
    seen = []
    original = soak._write_report

    def spy(output_dir, **kw):
        seen.append(kw["run_state"])
        return original(output_dir, **kw)

    soak._write_report = spy
    try:
        _run(tmp_path, "--duration-hours", "0.5", "--target-hz", "1", "--checkpoint-seconds", "300")
    finally:
        soak._write_report = original
    assert seen.count("RUNNING") >= 4 and seen[-1] == "FINAL"


def test_validation_rejects_missing_tampered_and_non_pass_reports(tmp_path):
    assert soak.validate_report(tmp_path / "nothing", min_hours=0, expected_commit=None)
    _run(tmp_path, "--duration-hours", "0.05", "--target-hz", "1")
    path = tmp_path / "out" / "live_soak_report.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["summary"]["status"] = "FAIL"
    data["summary"]["set_unchanged"] = False
    data["summary"]["final_identity"] = "SOMETHING ELSE"
    path.write_text(json.dumps(data), encoding="utf-8")
    problems = " | ".join(soak.validate_report(tmp_path / "out", min_hours=0, expected_commit=None))
    assert "status is 'FAIL'" in problems and "SET?" in problems and "identity" in problems


@pytest.mark.parametrize("argv", [
    ["--resource", "X", "--sources", "CH1,CH1"], ["--resource", "X", "--sources", "CH5"],
    ["--resource", "X", "--sample-seconds", "0.5"], ["--resource", "X", "--duration-hours", "0"],
    ["--resource", "X", "--max-failures", "-1"], [],
])
def test_bad_arguments_are_rejected(argv):
    with pytest.raises(SystemExit):
        soak.parse_args(argv)


def test_main_validate_mode_returns_an_exit_code(tmp_path, capsys):
    _run(tmp_path, "--duration-hours", "0.05", "--target-hz", "1")
    out = str(tmp_path / "out")
    assert soak.main(["--validate-report", out, "--min-hours", "0.04"]) == 0
    assert soak.main(["--validate-report", out, "--min-hours", "12"]) == 1
    assert "INVALID" in capsys.readouterr().out
