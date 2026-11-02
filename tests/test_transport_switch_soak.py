"""Deterministic offline tests for the USB/Ethernet 48-hour soak runner."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
_spec = importlib.util.spec_from_file_location(
    "run_transport_switch_soak", SCRIPTS / "run_transport_switch_soak.py"
)
assert _spec is not None and _spec.loader is not None
soak = importlib.util.module_from_spec(_spec)
sys.modules["run_transport_switch_soak"] = soak
_spec.loader.exec_module(soak)


IDN = "TEKTRONIX,DPO4054,C011280,CF:91.1CT FV:v2.68"


class SimClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(0.0, seconds)


class FakeScope:
    live = 0
    peak_live = 0

    def __init__(self, resource: str, identity: str = IDN) -> None:
        self.resource = resource
        self.identity = identity
        self.closed = False
        FakeScope.live += 1
        FakeScope.peak_live = max(FakeScope.peak_live, FakeScope.live)

    def query_identity(self) -> str:
        return self.identity

    def get_acquisition_state(self) -> str:
        return "RUN"

    def get_trigger_state(self) -> str:
        return "AUTO"

    def get_record_length(self) -> int:
        return 1_000

    def get_bus_waveform_count(self) -> int:
        return 0

    def get_reference_waveform_count(self) -> int:
        return 4

    def disconnect(self) -> None:
        if not self.closed:
            self.closed = True
            FakeScope.live -= 1


@pytest.fixture(autouse=True)
def _isolated_locks(monkeypatch, tmp_path):
    FakeScope.live = 0
    FakeScope.peak_live = 0
    monkeypatch.setattr(
        soak.base,
        "_lock_path",
        lambda resource: tmp_path / ("usb.lock" if resource.startswith("USB") else "tcp.lock"),
    )
    monkeypatch.setattr(soak.base, "_git_commit", lambda: "a" * 40)


def _args(tmp_path: Path, *extra: str):
    return soak.parse_args(
        [
            "--usb-resource",
            "USB0::SCOPE::INSTR",
            "--ethernet-resource",
            "TCPIP0::192.0.2.1::INSTR",
            "--duration-hours",
            "0.01",
            "--switch-minutes",
            "0.1",
            "--interval-seconds",
            "5",
            "--checkpoint-seconds",
            "10",
            "--output-dir",
            str(tmp_path / "out"),
            *extra,
        ]
    )


def _run(tmp_path: Path, *extra: str, factory=None):
    clock = SimClock()
    connections: list[str] = []

    def connect(resource: str, _timeout_ms: int):
        connections.append(resource)
        return (factory or FakeScope)(resource)

    code = soak.run_soak(_args(tmp_path, *extra), connect, clock=clock, sleep=clock.sleep)
    report = json.loads(
        (tmp_path / "out" / "transport_switch_soak_report.json").read_text(encoding="utf-8")
    )
    return code, report, connections


def test_soak_preflights_and_alternates_one_session_at_a_time(tmp_path):
    code, report, connections = _run(tmp_path)
    summary = report["summary"]
    assert code == 0, summary["failure_reasons"]
    assert summary["status"] == "PASS" and summary["run_state"] == "FINAL"
    assert summary["offline_operation"] is True
    assert len(summary["runner_sha256"]) == 64
    assert summary["worktree_dirty_at_start"] is True
    assert summary["planned_handoffs"] == summary["completed_handoffs"] == 5
    assert summary["samples_by_transport"]["usb"] > 0
    assert summary["samples_by_transport"]["ethernet"] > 0
    assert summary["preflight_identities"] == {"usb": IDN, "ethernet": IDN}
    assert summary["final_identities"] == {"usb": IDN, "ethernet": IDN}
    assert FakeScope.peak_live == 1 and FakeScope.live == 0
    # Two preflights, six slot activations and two final health checks.
    assert connections[:2] == ["USB0::SCOPE::INSTR", "TCPIP0::192.0.2.1::INSTR"]
    assert len(connections) == 10
    assert soak.validate_report(tmp_path / "out", min_hours=0.01) == []


def test_durable_journal_and_compact_running_checkpoints(tmp_path, monkeypatch):
    running_sample_lengths: list[int] = []
    original = soak.base._write_atomic_text

    def spy(path, content):
        if path.name == "transport_switch_soak_report.json":
            payload = json.loads(content)
            if payload["summary"]["run_state"] == "RUNNING":
                running_sample_lengths.append(len(payload["samples"]))
        original(path, content)

    monkeypatch.setattr(soak.base, "_write_atomic_text", spy)
    code, report, _ = _run(tmp_path)
    events = [
        json.loads(line)
        for line in (tmp_path / "out" / "transport_switch_events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert code == 0 and running_sample_lengths
    assert set(running_sample_lengths) == {0}
    assert len(report["samples"]) == report["summary"]["successful_samples"]
    assert events[0]["event"] == "run_started"
    assert events[-1]["event"] == "run_finished"
    assert sum(event["event"] == "sample" for event in events) == len(report["samples"])


def test_preflight_rejects_different_instrument_on_ethernet(tmp_path):
    def wrong(resource: str):
        identity = IDN if resource.startswith("USB") else IDN.replace("C011280", "OTHER")
        return FakeScope(resource, identity)

    code, report, _ = _run(tmp_path, factory=wrong)
    assert code == 1
    assert report["summary"]["status"] == "FAIL"
    assert any(
        "Transport identities differ" in reason for reason in report["summary"]["failure_reasons"]
    )
    assert FakeScope.live == 0


def test_failed_handoff_is_retried_but_final_result_fails_limit(tmp_path):
    calls = {"ethernet": 0}

    def flaky(resource: str):
        if resource.startswith("TCPIP"):
            calls["ethernet"] += 1
            # Call 1 is preflight.  Fail the first real Ethernet handoff only.
            if calls["ethernet"] == 2:
                raise TimeoutError("simulated Ethernet handoff timeout")
        return FakeScope(resource)

    code, report, _ = _run(
        tmp_path,
        "--duration-hours",
        "0.02",
        "--switch-minutes",
        "0.2",
        "--max-failures",
        "0",
        "--max-handoff-failures",
        "0",
        factory=flaky,
    )
    summary = report["summary"]
    assert code == 1 and summary["status"] == "FAIL"
    assert summary["failures"] == 1 and summary["handoff_failures"] == 1
    assert summary["completed_handoffs"] == summary["planned_handoffs"]
    assert summary["samples_by_transport"]["ethernet"] > 0


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--usb-resource", "TCPIP0::X::INSTR", "--ethernet-resource", "USB0::X::INSTR"],
        ["--usb-resource", "USB0::X", "--ethernet-resource", "TCPIP0::X", "--duration-hours", "0"],
        [
            "--usb-resource",
            "USB0::X",
            "--ethernet-resource",
            "TCPIP0::X",
            "--interval-seconds",
            "1",
        ],
    ],
)
def test_invalid_arguments_are_rejected(argv):
    with pytest.raises(SystemExit):
        soak.parse_args(argv)


def test_validator_rejects_running_or_short_report(tmp_path):
    _run(tmp_path)
    path = tmp_path / "out" / "transport_switch_soak_report.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["summary"]["status"] = "RUNNING"
    payload["summary"]["run_state"] = "RUNNING"
    path.write_text(json.dumps(payload), encoding="utf-8")
    problems = soak.validate_report(tmp_path / "out", min_hours=48)
    assert any("finalized PASS" in problem for problem in problems)
    assert any("shorter" in problem for problem in problems)
