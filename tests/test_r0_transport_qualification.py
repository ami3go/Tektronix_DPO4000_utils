"""Offline R0 safety, approval, raw-observation and reporting regression tests."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

from dpo4000_utils.baseline_compare import load_thresholds
from dpo4000_utils.r0_qualification import VerifiedSetupGuard
import dpo4000_utils.r0_qualification as r0
import dpo4000_utils.settings as settings


def _script(name: str):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"r0_qualification_test_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


reporting = _script("report_r0_transports")
comparing = _script("compare_r0_baseline")


class _FakeScope:
    def __init__(self) -> None:
        self.setup = "original setup"

    def query_identity(self) -> str:
        return "TEKTRONIX,DPO4054,SERIAL,FV:2.68"

    def ensure_connected(self):
        return self


class _FakeCapture:
    def __init__(self) -> None:
        self.scope = _FakeScope()

    def _require_scope(self):
        return self.scope

    def connect(self) -> None:
        if self.scope is None:
            self.scope = _FakeScope()


def _mock_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        r0, "build_scope_settings_payload",
        lambda scope: {"instrument": scope.query_identity(), "setup": scope.setup},
    )
    # The guard restores through settings.restore_setup_verified(), which looks these up
    # in the settings module.
    monkeypatch.setattr(settings, "read_scope_setup_string", lambda scope: scope.setup)
    monkeypatch.setattr(
        settings, "apply_setup_string",
        lambda scope, setup, **kwargs: setattr(scope, "setup", setup),
    )


def test_guard_recovers_original_setup_and_keeps_evidence(tmp_path: Path, monkeypatch) -> None:
    _mock_settings(monkeypatch)
    capture = _FakeCapture()
    with VerifiedSetupGuard(capture, tmp_path, capture.scope.query_identity()) as guard:
        capture.scope.setup = "changed setup"
    assert guard.report["status"] == "VERIFIED"
    assert json.loads((tmp_path / "r0_initial_setup.json").read_text())["setup"] == "original setup"
    assert json.loads((tmp_path / "r0_setup_restoration.json").read_text())["verified"] is True
    assert capture.scope.setup == "original setup"


def test_guard_cannot_certify_failed_restore(tmp_path: Path, monkeypatch) -> None:
    _mock_settings(monkeypatch)
    monkeypatch.setattr(settings, "apply_setup_string", lambda scope, setup, **kwargs: None)
    capture = _FakeCapture()
    with pytest.raises(RuntimeError, match="NOT verified"):
        with VerifiedSetupGuard(
            capture, tmp_path, capture.scope.query_identity(),
            settle_timeout_s=0.05, poll_interval_s=0.01,
        ):
            capture.scope.setup = "changed"
    assert json.loads((tmp_path / "r0_setup_restoration.json").read_text())["status"] == "RESTORATION_FAILED"


def test_guard_requires_exact_bench_identity_before_writes(tmp_path: Path, monkeypatch) -> None:
    _mock_settings(monkeypatch)
    with pytest.raises(RuntimeError, match="identity mismatch"):
        with VerifiedSetupGuard(_FakeCapture(), tmp_path, "TEKTRONIX,DPO4054,WRONG,FW"):
            pass
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0])
def test_thresholds_reject_nonfinite_or_negative_limits(value: float) -> None:
    with pytest.raises(ValueError):
        load_thresholds({"operations": {"connection": {
            "absolute_tolerance_s": 0.1, "relative_limit": value,
        }}})
    with pytest.raises(ValueError):
        load_thresholds({"operations": {"connection": {
            "absolute_tolerance_s": value, "relative_limit": 1.3,
        }}})


def test_missing_raw_or_1m_waveform_does_not_pass() -> None:
    observations = {"connection": {"p95": 0.1, "sample_count": 20}}
    findings = comparing._timing_quality_issues(observations, "baseline")
    assert any("raw" in issue for issue in findings)
    assert any("1000000" in issue for issue in findings)


def test_transport_rollup_with_no_physical_reports_is_blocked(tmp_path: Path) -> None:
    result, rows = reporting.evaluate(tmp_path, tmp_path / "missing-thresholds.json", None)
    assert result["status"] == "BLOCKED"
    assert result["issues"]
    assert rows == []


def test_rollup_rejects_fabricated_samples() -> None:
    assert not reporting._raw_ok({"samples_s": [1, float("nan")], "sample_count": 2,
                                  "p50": 1, "p95": 1, "max": 1})
    assert not reporting._raw_ok({"samples_s": [1], "sample_count": 2,
                                  "p50": 1, "p95": 1, "max": 1})


def test_guard_waits_for_the_scope_to_settle_before_judging_the_restore(tmp_path: Path, monkeypatch) -> None:
    """A transient read-back (cursor positions) must not be reported as a failed restoration."""
    _mock_settings(monkeypatch)
    reads = {"count": 0}

    def transient_read(scope):
        reads["count"] += 1
        # Wrong for the first three reads after the restore write, then settled.
        return scope.setup if scope.setup != "original setup" or reads["count"] > 4 else "original setup;UNSETTLED"

    monkeypatch.setattr(settings, "read_scope_setup_string", transient_read)
    capture = _FakeCapture()
    with VerifiedSetupGuard(
        capture, tmp_path, capture.scope.query_identity(), settle_timeout_s=5.0, poll_interval_s=0.001
    ) as guard:
        capture.scope.setup = "changed setup"
    assert guard.report["status"] == "VERIFIED"
    assert guard.report["restore_passes"] == 1
