from __future__ import annotations

import json
from pathlib import Path

from dpo4000_utils.hardware_verification_core import (
    LIFECYCLE_FUNCTION_COVERS,
    PURE_FUNCTION_COVERS,
    WAVEFORM_FUNCTION_COVERS,
)
from dpo4000_utils.hardware_verification import (
    HardwareVerifier,
    PUBLIC_FUNCTION_RISK,
    PUBLIC_METHOD_RISK,
    VerificationCase,
    VerificationConfig,
    VerificationResult,
    VerificationRisk,
    public_driver_methods,
    public_package_functions,
    verification_manifest_gaps,
)


def _verifier(tmp_path: Path, profile: VerificationRisk = VerificationRisk.READ_ONLY):
    return HardwareVerifier(
        VerificationConfig(
            resource="USB0::TEST::INSTR",
            output_dir=tmp_path,
            profile=profile,
        )
    )


def test_hardware_verification_manifest_matches_public_api_exactly():
    assert verification_manifest_gaps() == {"methods": [], "functions": []}
    assert set(PUBLIC_METHOD_RISK) == public_driver_methods()
    assert set(PUBLIC_FUNCTION_RISK) == public_package_functions()


def test_every_public_package_function_is_covered_by_a_case():
    """An uncovered symbol is reported UNVERIFIED and makes the verifier exit 1."""
    groups = (PURE_FUNCTION_COVERS, LIFECYCLE_FUNCTION_COVERS, WAVEFORM_FUNCTION_COVERS)
    covered = [name for group in groups for name in group]
    assert len(covered) == len(set(covered)), "a function is claimed by two cases"
    assert set(covered) == public_package_functions()


def test_pure_function_case_exercises_framework_helpers_offline(tmp_path):
    detail = _verifier(tmp_path)._case_pure_functions()
    assert "passed" in detail


def test_pure_function_case_fails_when_a_helper_is_broken(tmp_path, monkeypatch):
    import dpo4000_utils as public_api

    monkeypatch.setattr(public_api, "recipe_result_values", lambda _result: {})
    try:
        _verifier(tmp_path)._case_pure_functions()
    except (AssertionError, KeyError):
        return
    raise AssertionError("a broken helper must fail the pure-function case")


def test_reduced_profile_skips_write_case_without_executing_callback(tmp_path):
    verifier = _verifier(tmp_path, VerificationRisk.READ_ONLY)
    called = False

    def callback():
        nonlocal called
        called = True

    verifier._register_and_run(
        VerificationCase(
            "write-case",
            "Write case",
            VerificationRisk.REVERSIBLE,
            covers_methods=("set_channel_label",),
        ),
        callback,
    )

    assert called is False
    assert verifier.results[0].status == "SKIP"
    assert verifier._write_case_ran is False


def test_write_case_marks_restore_required_before_callback_failure(tmp_path):
    verifier = _verifier(tmp_path, VerificationRisk.REVERSIBLE)

    def callback():
        raise RuntimeError("simulated write failure")

    verifier._register_and_run(
        VerificationCase(
            "write-case",
            "Write case",
            VerificationRisk.REVERSIBLE,
            covers_methods=("set_channel_label",),
        ),
        callback,
    )

    assert verifier._write_case_ran is True
    assert verifier.results[0].status == "FAIL"
    assert verifier.results[0].error_type == "RuntimeError"


def test_report_files_include_case_and_api_coverage(tmp_path):
    verifier = _verifier(tmp_path)
    verifier.idn = "TEKTRONIX,DPO4054,TEST,1.0"
    verifier._register_and_run(
        VerificationCase(
            "identity",
            "Identity",
            VerificationRisk.READ_ONLY,
            covers_methods=("query_identity",),
        ),
        lambda: "identity ok",
    )
    verifier.finished_at = verifier.started_at

    report = verifier.build_report()
    verifier.write_report_files(report)

    json_path = tmp_path / "verification_report.json"
    markdown_path = tmp_path / "verification_report.md"
    html_path = tmp_path / "verification_report.html"
    assert json_path.exists()
    assert markdown_path.exists()
    assert html_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["idn"].startswith("TEKTRONIX")
    assert any(item["symbol"] == "query_identity" for item in payload["methods"])
    assert "DPO4000 Real-Hardware Verification Report" in markdown_path.read_text(
        encoding="utf-8"
    )
    assert "Public driver methods" in html_path.read_text(encoding="utf-8")


def test_exit_code_fails_for_failed_case_or_unverified_api(tmp_path):
    verifier = _verifier(tmp_path)
    verifier.finished_at = verifier.started_at
    report = verifier.build_report()
    assert report["api_totals"]["unverified"] > 0
    assert verifier.exit_code(report) == 1

    verifier.results.append(
        VerificationResult(
            case_id="simulated-failure",
            title="Simulated failure",
            risk="read-only",
            status="FAIL",
            duration_s=0.0,
            error_type="RuntimeError",
            error_message="simulated",
        )
    )
    report = verifier.build_report()
    assert verifier.exit_code(report) == 1
