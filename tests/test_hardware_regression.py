from __future__ import annotations

from copy import deepcopy

import pytest

from dpo4000_utils.hardware_regression import (
    build_hardware_baseline,
    compare_hardware_reports,
)


def _report(
    durations: dict[str, float],
    *,
    elapsed_s: float = 10.0,
    resource: str = "TCPIP0::192.168.0.5::INSTR",
    idn: str = "TEKTRONIX,DPO4054,C011280,CF:91.1CT FV:v2.68",
) -> dict:
    statuses = {
        "fixture-probe-comp": "PASS",
        "A1-periodic-image": "PASS",
        "A2-image-on-trigger": "PASS",
        "logger-bus": "SKIP",
        "scope-restore": "PASS",
    }
    results = []
    for case_id, status in statuses.items():
        results.append(
            {
                "case_id": case_id,
                "title": case_id,
                "group": "fixture" if "fixture" in case_id or "restore" in case_id else "automation",
                "status": status,
                "duration_s": float(durations.get(case_id, 0.01)),
            }
        )
    return {
        "schema_version": 1,
        "status": "PASS",
        "elapsed_s": float(elapsed_s),
        "resource": resource,
        "idn": idn,
        "package_version": "0.8.0",
        "platform": "Windows-test",
        "config": {
            "resource": resource,
            "output_dir": "ignored",
            "channel": 1,
            "timeout_ms": 60_000,
            "trigger_timeout_s": 10.0,
            "waveform_points": 1_000,
            "expected_frequency_hz": 1_000.0,
            "frequency_tolerance_fraction": 0.35,
            "min_vpp_v": 0.5,
            "max_vpp_v": 5.0,
            "hardcopy": True,
            "suite": "all",
        },
        "counts": {"PASS": 4, "FAIL": 0, "SKIP": 1},
        "results": results,
    }


def _repeated(case_duration: float = 1.0, elapsed_s: float = 10.0) -> list[dict]:
    reports = []
    for offset in (-0.04, -0.02, 0.0, 0.02, 0.04):
        reports.append(
            _report(
                {
                    "fixture-probe-comp": 0.8 + offset,
                    "A1-periodic-image": case_duration + offset,
                    "A2-image-on-trigger": 1.4 + offset,
                    "scope-restore": 3.0 + offset,
                },
                elapsed_s=elapsed_s + offset,
            )
        )
    return reports


def test_build_hardware_baseline_contains_distribution_and_contract() -> None:
    reports = _repeated()
    baseline = build_hardware_baseline(
        reports,
        resource="TCPIP0::192.168.0.5::INSTR",
    )

    assert baseline["schema_version"] == 1
    assert baseline["repetitions"] == 5
    assert baseline["resource_family"] == "TCPIP"
    assert baseline["idn"].startswith("TEKTRONIX,DPO4054")
    assert baseline["fixture"]["channel"] == 1
    assert baseline["cases"]["logger-bus"]["expected_status"] == "SKIP"
    assert baseline["cases"]["A1-periodic-image"]["timing"]["sample_count"] == 5
    assert baseline["run_timing"]["timing"]["p95"] > 0.0


def test_compare_accepts_same_tcpip_family_and_normal_noise() -> None:
    baseline = build_hardware_baseline(
        _repeated(case_duration=1.0, elapsed_s=10.0),
        resource="TCPIP0::192.168.0.5::INSTR",
    )
    candidate = _repeated(case_duration=1.18, elapsed_s=10.8)
    for report in candidate:
        report["resource"] = "TCPIP1::10.10.10.10::INSTR"
        report["config"]["resource"] = report["resource"]

    result = compare_hardware_reports(
        baseline,
        candidate,
        resource="TCPIP1::10.10.10.10::INSTR",
        relative_limit=1.30,
        case_absolute_tolerance_s=0.25,
        total_absolute_tolerance_s=2.0,
    )

    assert result["passed"]
    assert result["status"] == "PASS"
    assert result["failures"] == []
    assert not result["cases"]["A1-periodic-image"]["regressed"]


def test_compare_fails_case_only_when_relative_and_absolute_limits_are_exceeded() -> None:
    baseline = build_hardware_baseline(
        _repeated(case_duration=1.0),
        resource="TCPIP0::192.168.0.5::INSTR",
    )

    relative_only = compare_hardware_reports(
        baseline,
        _repeated(case_duration=1.32),
        resource="TCPIP0::192.168.0.5::INSTR",
        relative_limit=1.30,
        case_absolute_tolerance_s=0.50,
    )
    assert relative_only["passed"]

    both = compare_hardware_reports(
        baseline,
        _repeated(case_duration=1.45),
        resource="TCPIP0::192.168.0.5::INSTR",
        relative_limit=1.30,
        case_absolute_tolerance_s=0.25,
    )
    assert not both["passed"]
    assert both["cases"]["A1-periodic-image"]["regressed"]
    assert any("A1-periodic-image p95 regression" in item for item in both["failures"])


def test_compare_fails_whole_run_regression() -> None:
    baseline = build_hardware_baseline(
        _repeated(elapsed_s=10.0),
        resource="TCPIP0::192.168.0.5::INSTR",
    )
    result = compare_hardware_reports(
        baseline,
        _repeated(elapsed_s=14.0),
        resource="TCPIP0::192.168.0.5::INSTR",
        relative_limit=1.30,
        total_absolute_tolerance_s=2.0,
    )

    assert not result["passed"]
    assert result["run_timing"]["regressed"]
    assert any("Whole-run p95 regression" in item for item in result["failures"])


def test_compare_rejects_usb_against_tcpip_baseline() -> None:
    baseline = build_hardware_baseline(
        _repeated(),
        resource="TCPIP0::192.168.0.5::INSTR",
    )
    candidate = _repeated()
    for report in candidate:
        report["resource"] = "USB0::0x0699::0x0401::C011280::INSTR"
        report["config"]["resource"] = report["resource"]

    result = compare_hardware_reports(
        baseline,
        candidate,
        resource="USB0::0x0699::0x0401::C011280::INSTR",
    )

    assert not result["passed"]
    assert any("Resource interface family differs" in item for item in result["failures"])


def test_compare_fails_when_fixture_configuration_changes() -> None:
    baseline = build_hardware_baseline(
        _repeated(),
        resource="TCPIP0::192.168.0.5::INSTR",
    )
    candidate = _repeated()
    for report in candidate:
        report["config"]["waveform_points"] = 10_000

    result = compare_hardware_reports(
        baseline,
        candidate,
        resource="TCPIP0::192.168.0.5::INSTR",
    )

    assert not result["passed"]
    assert "Probe Comp fixture/config differs from baseline" in result["failures"]


def test_baseline_creation_rejects_failed_or_unstable_hil_sets() -> None:
    failed = _repeated()
    failed[0]["results"][1]["status"] = "FAIL"
    with pytest.raises(ValueError, match="FAIL cases"):
        build_hardware_baseline(failed, resource="TCPIP0::192.168.0.5::INSTR")

    unstable = _repeated()
    unstable[3] = deepcopy(unstable[3])
    unstable[3]["results"][1]["status"] = "SKIP"
    with pytest.raises(ValueError, match="case/status set differs"):
        build_hardware_baseline(unstable, resource="TCPIP0::192.168.0.5::INSTR")
