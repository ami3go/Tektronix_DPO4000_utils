"""Adversarial P0 review regressions; no VISA connection or physical hardware."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _script(name: str):
    spec = importlib.util.spec_from_file_location("independent_" + name, SCRIPTS / (name + ".py"))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


release = _script("evaluate_p0_release")
validator = _script("validate_soak_report")
COMMIT = "a" * 40
IDN = "TEKTRONIX,DPO4054,C011280,FV:2.0"


def _json(root: Path, relative: str, item: dict) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(item, allow_nan=False), encoding="utf-8")
    return path


def _soak_claim(root: Path, *, samples: list[dict] | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    samples = samples if samples is not None else [{
        "cycle": 1, "elapsed_s": 86390.0, "identity": IDN,
        "cycle_duration_s": 0.01, "python_current_bytes": 100,
        "thread_count": 1,
    }]
    summary = {
        "schema_version": 2, "run_state": "FINAL", "status": "PASS",
        "started_at": "2026-10-22T00:00:00+00:00",
        "finished_at": "2026-10-23T00:00:00+00:00",
        "elapsed_s": 86400.0, "requested_duration_hours": 24.0,
        "interval_seconds": 10.0, "expected_cycles": 8640,
        "missed_deadlines": 0, "baseline_identity": IDN,
        "final_identity": IDN, "resource": "USB0::SCOPE::INSTR",
        "commit_sha": COMMIT, "cleanup_errors": [], "failure_reasons": [],
        "successful_samples": len(samples), "cycles": len(samples), "failures": 0,
        "acceptance_limits": {
            "max_missed_deadlines": 10, "max_failures": 10,
            "max_cycle_latency_s": 60.0, "max_rss_growth_mib": 256.0,
            "max_python_growth_mib": 64.0, "max_fd_growth": 8,
            "max_thread_growth": 4, "max_latency_drift_factor": 3.0,
        },
    }
    _json(root, "soak_report.json", {"summary": summary, "samples": samples, "failures": []})
    (root / "soak_report.md").write_text(
        "# DPO4000 hardware soak qualification\n\n**Status:** PASS\n",
        encoding="utf-8",
    )
    return root


def test_one_cycle_cannot_claim_completed_24_hour_soak(tmp_path: Path) -> None:
    problems, hashes = validator.validate_soak_report(_soak_claim(tmp_path))
    assert hashes["json"] and hashes["markdown"]
    assert any("Scheduled sample coverage incomplete" in issue for issue in problems)


def test_duplicate_json_key_does_not_override_failed_soak(tmp_path: Path) -> None:
    _soak_claim(tmp_path)
    (tmp_path / "soak_report.json").write_text(
        '{"summary":{"status":"FAIL"},"summary":{"status":"PASS"}}',
        encoding="utf-8",
    )
    problems, _ = validator.validate_soak_report(tmp_path)
    assert any("Duplicate JSON key" in issue for issue in problems)


def test_wall_time_mismatch_cannot_claim_pass(tmp_path: Path) -> None:
    _soak_claim(tmp_path)
    doc = json.loads((tmp_path / "soak_report.json").read_text(encoding="utf-8"))
    doc["summary"]["finished_at"] = "2026-10-22T00:00:05+00:00"
    _json(tmp_path, "soak_report.json", doc)
    problems, _ = validator.validate_soak_report(tmp_path)
    assert any("Wall duration contradicts" in issue for issue in problems)


@pytest.mark.skipif(os.name == "nt", reason="Windows symlink creation may require privileges")
def test_soak_symlink_evidence_is_rejected(tmp_path: Path) -> None:
    _soak_claim(tmp_path)
    real = tmp_path / "real.json"
    (tmp_path / "soak_report.json").rename(real)
    (tmp_path / "soak_report.json").symlink_to(real)
    problems, _ = validator.validate_soak_report(tmp_path)
    assert any("Symlink" in issue for issue in problems)


def test_forged_ci_pass_has_no_provenance(tmp_path: Path) -> None:
    jobs = {
        name: {"status": "PASS", "commit_sha": COMMIT, "url": "https://example.org/green"}
        for name in release.REQUIRED_CI
    }
    _json(tmp_path, "software/ci.json", {
        "schema_version": 1, "commit_sha": COMMIT, "jobs": jobs,
    })
    manifest = release.evaluate(tmp_path, commit=COMMIT)
    assert manifest["gates"]["P0-G0"]["state"] == "FAIL"
    assert "exact-head" in " ".join(manifest["gates"]["P0-G0"]["reasons"])


def test_incomplete_hil_and_fake_skip_cannot_pass(tmp_path: Path) -> None:
    evidence_path = tmp_path / "hardware/case.log"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("bench fixture only", encoding="utf-8")
    cases = [
        {"id": name, "status": "PASS", "artifact": "hardware/case.log"}
        for name in release.REQUIRED_HIL
    ]
    cases[0]["status"] = "SKIP"
    cases[0]["capability_absent"] = True
    cases[0]["reason"] = "claimed unsupported"
    _json(tmp_path, "hardware/qualification.json", {
        "schema_version": 1, "commit_sha": COMMIT, "idn": IDN,
        "setup_restored": True, "cases": cases,
    })
    gate = release.evaluate(tmp_path, commit=COMMIT)["gates"]["P0-G1"]
    assert gate["state"] == "FAIL"
    assert "not PASS" in " ".join(gate["reasons"])


@pytest.mark.skipif(os.name == "nt", reason="Windows symlink creation may require privileges")
def test_hil_symlink_does_not_count_as_evidence(tmp_path: Path) -> None:
    real = _json(tmp_path, "hardware/actual.json", {"evidence": "fixture"})
    (tmp_path / "hardware/alias.json").symlink_to(real)
    _json(tmp_path, "hardware/qualification.json", {
        "schema_version": 1, "commit_sha": COMMIT, "idn": IDN,
        "setup_restored": True,
        "cases": [
            {"id": name, "status": "PASS", "artifact": "hardware/alias.json"}
            for name in release.REQUIRED_HIL
        ],
    })
    gate = release.evaluate(tmp_path, commit=COMMIT)["gates"]["P0-G1"]
    assert gate["state"] == "FAIL"
    assert "unsafe HIL artifact" in " ".join(gate["reasons"])


def test_reported_performance_pass_without_raw_coverage_fails(tmp_path: Path) -> None:
    for transport in ("usb", "tcpip"):
        base = "performance/" + transport
        visa = "USB0" if transport == "usb" else "TCPIP0"
        candidates = {}
        for kind in ("functional", "timing"):
            baseline = {
                "schema_version": 1, "idn": IDN,
                "resource": visa + "::SCOPE::INSTR", "commit_sha": "b" * 40,
            }
            candidate = {**baseline, "commit_sha": COMMIT}
            if kind == "timing":
                baseline["operations"] = {}
                candidate["operations"] = {}
            _json(tmp_path, base + "/baseline/r0_" + kind + "_baseline.json", baseline)
            candidate_path = _json(tmp_path, base + "/candidate/r0_candidate_" + kind + ".json", candidate)
            candidates[kind] = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
        _json(tmp_path, base + "/candidate/comparison_report.json", {
            "status": "PASS", "identity_issues": [], "missing_operations": [],
            "unthresholded_operations": [], "known_coverage_gaps": [],
            "functional_diffs": [], "timing_regressions": [],
            "candidate_functional_sha256": candidates["functional"],
            "candidate_timing_sha256": candidates["timing"],
        })
        for destination in ("candidate", "baseline"):
            _json(tmp_path, base + "/" + destination + "/r0_extra_metrics.json", {
                "metrics": {"synthetic_test_only": 1},
            })
    policy = ROOT / "tests/baselines/r0_timing_thresholds.json"
    _json(tmp_path, "performance/transport_comparison/transport_comparison.json", {
        "schema_version": 1, "status": "PASS",
        "threshold_sha256": hashlib.sha256(policy.read_bytes()).hexdigest(),
        "threshold_approval": {"status": "APPROVED"},
        "artifacts_sha256": {},
    })
    gate = release.evaluate(tmp_path, commit=COMMIT)["gates"]["P0-G2"]
    assert gate["state"] == "FAIL"
    assert "zero timing coverage" in " ".join(gate["reasons"])


def test_empty_junit_suite_cannot_satisfy_a25(tmp_path: Path) -> None:
    _json(tmp_path, "a25/qualification.json", {
        "commit_sha": COMMIT, "review_status": "APPROVED",
        "installed_cli": True, "session_released": True,
    })
    _json(tmp_path, "a25/hardware-cli-report.json", {
        "commit_sha": COMMIT, "status": "pass", "exit_code": 0, "identity": IDN,
    })
    (tmp_path / "a25/hardware-junit.xml").write_text(
        '<testsuite tests="1" failures="0" errors="0" skipped="0"/>',
        encoding="utf-8",
    )
    gate = release.evaluate(tmp_path, commit=COMMIT)["gates"]["P0-G4"]
    assert gate["state"] == "FAIL"
    assert "no real hardware test cases" in " ".join(gate["reasons"])


def test_review_without_approval_url_is_not_approved(tmp_path: Path) -> None:
    _json(tmp_path, "review.json", {
        "commit_sha": COMMIT, "status": "APPROVED", "reviewer": "someone",
        "critical_open": 0, "high_open": 0,
    })
    gate = release.evaluate(tmp_path, commit=COMMIT)["gates"]["REVIEW"]
    assert gate["state"] == "FAIL"


def test_release_evaluation_does_not_open_visa(tmp_path: Path, monkeypatch) -> None:
    import pyvisa

    def forbidden_resource_manager(*_args, **_kwargs):
        raise AssertionError("Offline release evaluator attempted VISA I/O")

    monkeypatch.setattr(pyvisa, "ResourceManager", forbidden_resource_manager)
    manifest = release.evaluate(tmp_path, commit=COMMIT)
    assert manifest["overall"] == "BLOCKED"
    assert all(item["state"] != "PASS" for item in manifest["gates"].values())


def test_waveform_and_hardcopy_calls_are_not_classified_read_only() -> None:
    from dpo4000_utils.hardware_verification import PUBLIC_METHOD_RISK, VerificationRisk

    for name in (
        "read_waveform", "read_channel_waveform_data", "read_enabled_waveforms",
        "read_screen_png", "save_image_path",
    ):
        assert PUBLIC_METHOD_RISK[name] >= VerificationRisk.REVERSIBLE


def test_reported_p95_cannot_contradict_raw_monotonic_samples() -> None:
    samples = [0.01, 0.02, 0.03, 0.04, 0.05]
    record = {
        "samples_s": samples,
        "sample_count": len(samples),
        "min": 0.01, "max": 0.05,
        "p50": 0.03, "p95": 0.01,  # impossible, yet below an R0 threshold
        "timeout_count": 0, "error_count": 0,
    }
    ops = {"connection": record, "waveform_acquisition": {
        str(size): {**record, "p95": 0.05}
        for size in (1000, 10000, 100000, 1000000)
    }}
    issues = release._raw_timing_issues(ops, "forged")
    assert any("reported p95 contradicts raw samples: connection" in issue
               for issue in issues)


def test_verifier_requires_exact_scope_setup_restore_readback(tmp_path: Path, monkeypatch) -> None:
    from dpo4000_utils import hardware_verification_core as core

    class FakeScope:
        def ensure_connected(self):
            return object()

    verifier = core.HardwareVerifier(core.VerificationConfig(
        resource="USB0::FAKE::INSTR", output_dir=tmp_path
    ))
    verifier.scope = FakeScope()
    verifier.baseline_payload = {"instrument": IDN, "setup": "ACQUIRE:STATE ON"}
    writes = []
    monkeypatch.setattr(core, "apply_setup_string", lambda _session, command, **_kw:
                        writes.append(command))
    monkeypatch.setattr(core, "build_scope_settings_payload", lambda _session: {
        "instrument": IDN, "setup": "ACQUIRE:STATE OFF"
    })
    with pytest.raises(AssertionError, match="readback differs"):
        verifier._restore_baseline()
    assert writes == ["ACQUIRE:STATE ON"]


def test_rejected_hardware_preflight_cannot_fall_through_to_pytest() -> None:
    workflow = (ROOT / ".github/workflows/hardware-api-tests.yml").read_text(
        encoding="utf-8"
    )
    assert "if: steps.verifier.outcome == 'success'" in workflow
    assert "if: always()\n        run: pytest" not in workflow
    assert "dpo4000-physical-bench" in workflow


def test_unapproved_soak_is_a_failed_job_not_a_successful_skip() -> None:
    workflow = (ROOT / ".github/workflows/hardware-soak.yml").read_text(
        encoding="utf-8"
    )
    assert "BENCH_APPROVED" in workflow
    assert "exit 1" in workflow
    assert "if: ${{ inputs.authorized_bench }}" not in workflow
    assert "dpo4000-physical-bench" in workflow


def test_missing_exact_idn_blocks_invasive_hil_before_visa(monkeypatch, tmp_path: Path) -> None:
    from dpo4000_utils import hardware_verification_core as core

    def forbidden_connect(*_args, **_kwargs):
        raise AssertionError("Unauthorized verifier attempted VISA construction")

    monkeypatch.setattr(core, "DPO4054", forbidden_connect)
    verifier = core.HardwareVerifier(core.VerificationConfig(
        resource="USB0::RESERVED::INSTR",
        output_dir=tmp_path,
        profile=core.VerificationRisk.REVERSIBLE,
        expected_idn="TEKTRONIX",
    ))
    with pytest.raises(ValueError, match="exact DPO4054"):
        verifier.run()


def test_manual_hardware_workflow_requires_bench_reservation_and_serial() -> None:
    workflow = (ROOT / ".github/workflows/hardware-api-tests.yml").read_text(
        encoding="utf-8"
    )
    assert "BENCH_APPROVED" in workflow
    assert "TARGET_IDN" in workflow
    assert '--expected-idn "' in workflow
    assert "default: \"none\"" in workflow


def test_hil_artifact_hash_mismatch_cannot_claim_coverage(tmp_path: Path) -> None:
    artifact = tmp_path / "hardware/case.log"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("fake physical evidence", encoding="utf-8")
    _json(tmp_path, "hardware/qualification.json", {
        "schema_version": 1, "commit_sha": COMMIT,
        "idn": IDN, "setup_restored": True,
        "cases": [
            {
                "id": name, "status": "PASS",
                "artifact": "hardware/case.log",
                "artifact_sha256": "0" * 64,
            }
            for name in release.REQUIRED_HIL
        ],
    })
    gate = release.evaluate(tmp_path, commit=COMMIT)["gates"]["P0-G1"]
    assert gate["state"] == "FAIL"
    assert "SHA256 missing/mismatch" in " ".join(gate["reasons"])
