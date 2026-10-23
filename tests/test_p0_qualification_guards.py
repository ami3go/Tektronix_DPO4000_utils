"""P0 qualification guardrail tests: no VISA or hardware access."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from scripts.capture_r0_baseline import _write_new_baseline
from scripts.compare_r0_baseline import _identity_differences
from scripts.run_hardware_soak import (
    SoakSample,
    _acquire_lock,
    _lock_path,
    _write_report,
)


def _baseline(resource: str, idn: str = "TEKTRONIX,DPO4054,SERIAL,FW") -> dict:
    return {"resource": resource, "idn": idn, "operations": {}}


def test_r0_baseline_cannot_be_overwritten(tmp_path: Path) -> None:
    target = tmp_path / "r0_functional_baseline.json"
    _write_new_baseline(target, {"status": "known-good", "latency": 1})
    before = target.read_bytes()
    with pytest.raises(FileExistsError):
        _write_new_baseline(target, {"status": "regression", "latency": 999})
    assert target.read_bytes() == before
    assert json.loads(target.read_text(encoding="utf-8"))["latency"] == 1


def test_r0_baseline_serializes_only_standard_json(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _write_new_baseline(tmp_path / "bad.json", {"latency": float("nan")})
    assert not (tmp_path / "bad.json").exists()


@pytest.mark.parametrize(
    ("resource_a", "resource_b", "idn_b", "expect_issue"),
    [
        ("USB0::SCOPE::INSTR", "TCPIP0::SCOPE::INSTR", "TEKTRONIX,DPO4054,SERIAL,FW", True),
        ("USB0::SCOPE::INSTR", "USB0::SCOPE::INSTR", "TEKTRONIX,DPO4054,OTHER,FW", True),
        ("USB0::SCOPE::INSTR", "USB0::SCOPE::INSTR", "TEKTRONIX,DPO4054,SERIAL,FW", False),
    ],
)
def test_r0_transport_and_instrument_identity_fail_closed(
    resource_a: str, resource_b: str, idn_b: str, expect_issue: bool
) -> None:
    a = _baseline(resource_a)
    b = _baseline(resource_b, idn_b)
    issues = _identity_differences(a, a, b, b)
    assert bool(issues) == expect_issue


def test_soak_resource_lock_prevents_concurrent_runner(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("scripts.run_hardware_soak._lock_path", lambda _r: tmp_path / "scope.lock")
    lock = _acquire_lock("USB0::SCOPE::INSTR")
    try:
        with pytest.raises(FileExistsError):
            _acquire_lock("USB0::SCOPE::INSTR")
        assert "pid=" in lock.read_text(encoding="utf-8")
    finally:
        lock.unlink()


def test_soak_report_is_machine_readable_and_tracks_identity(tmp_path: Path) -> None:
    args = argparse.Namespace(
        duration_hours=24.0, interval_seconds=10.0,
        resource="USB0::SCOPE::INSTR",
    )
    sample = SoakSample(
        timestamp="2026-10-23T00:00:00+00:00",
        elapsed_s=86400.0, cycle=1,
        identity="TEKTRONIX,DPO4054,SERIAL,FW",
        acquisition_state="RUN", trigger_state="AUTO",
        record_length=1000, bus_count=0, reference_count=4,
        rss_bytes=1024, python_current_bytes=10, python_peak_bytes=20,
        thread_count=1, fd_count=5, cycle_duration_s=0.01,
    )
    _write_report(
        tmp_path, args=args, samples=[sample], failures=[], reconnects=0,
        cleanup_errors=[], started_at="2026-10-22T00:00:00+00:00",
        elapsed_s=86400, passed=True, reasons=[],
        status="PASS", baseline_identity=sample.identity, final_identity=sample.identity,
    )
    data = json.loads((tmp_path / "soak_report.json").read_text(encoding="utf-8"))
    assert data["summary"]["status"] == "PASS"
    assert data["summary"]["run_state"] == "FINAL"
    assert data["summary"]["baseline_identity"] == data["summary"]["final_identity"]
    assert data["summary"]["cycle_latency_p50_s"] == sample.cycle_duration_s
    assert "Status:** PASS" in (tmp_path / "soak_report.md").read_text(encoding="utf-8")


def test_soak_running_checkpoint_cannot_claim_pass(tmp_path: Path) -> None:
    args = argparse.Namespace(duration_hours=24.0, interval_seconds=10.0, resource="USB0::INSTR")
    _write_report(
        tmp_path, args=args, samples=[], failures=[], reconnects=0,
        cleanup_errors=[], started_at="2026-10-23T00:00:00+00:00",
        elapsed_s=120, passed=False, reasons=["Qualification still running"],
        status="RUNNING", run_state="RUNNING",
    )
    data = json.loads((tmp_path / "soak_report.json").read_text(encoding="utf-8"))
    assert data["summary"]["status"] == "RUNNING"
    assert data["summary"]["run_state"] != "FINAL"
