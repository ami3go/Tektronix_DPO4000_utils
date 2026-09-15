"""R0 hardware performance baseline creation/comparison for Probe-Comp HIL."""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .bench_hil import AutomationLoggerHilRunner, FAIL, HilConfig, PASS
from .regression import PerformanceGate, TimingSummary, linear_slope, summarize_timings

HARDWARE_BASELINE_SCHEMA_VERSION = 1
DEFAULT_BASELINE_REPETITIONS = 5
DEFAULT_RELATIVE_LIMIT = 1.30
DEFAULT_CASE_ABSOLUTE_TOLERANCE_S = 0.25
DEFAULT_TOTAL_ABSOLUTE_TOLERANCE_S = 2.0


@dataclass(frozen=True)
class HardwareRegressionOptions:
    """Common Probe-Comp R0 hardware regression options."""

    resource: str
    output_dir: Path
    baseline_path: Path
    repetitions: int | None = None
    channel: int = 1
    timeout_ms: int = 60_000
    trigger_timeout_s: float = 10.0
    waveform_points: int = 1_000
    expected_frequency_hz: float = 1_000.0
    frequency_tolerance_fraction: float = 0.35
    min_vpp_v: float = 0.5
    max_vpp_v: float = 5.0
    hardcopy: bool = True
    suite: str = "all"
    relative_limit: float = DEFAULT_RELATIVE_LIMIT
    case_absolute_tolerance_s: float = DEFAULT_CASE_ABSOLUTE_TOLERANCE_S
    total_absolute_tolerance_s: float = DEFAULT_TOTAL_ABSOLUTE_TOLERANCE_S

    def __post_init__(self) -> None:
        resource = str(self.resource).strip()
        if not resource:
            raise ValueError("resource cannot be empty")
        object.__setattr__(self, "resource", resource)
        object.__setattr__(self, "output_dir", Path(self.output_dir).expanduser().resolve())
        object.__setattr__(self, "baseline_path", Path(self.baseline_path).expanduser().resolve())
        if self.repetitions is not None:
            value = int(self.repetitions)
            if value < 2 or value > 100:
                raise ValueError("repetitions must be between 2 and 100")
            object.__setattr__(self, "repetitions", value)
        if self.suite not in {"all", "automation", "logger"}:
            raise ValueError("suite must be all, automation, or logger")
        if self.channel not in range(1, 5):
            raise ValueError("channel must be 1..4")
        for name in (
            "relative_limit",
            "case_absolute_tolerance_s",
            "total_absolute_tolerance_s",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, value)
        if self.relative_limit < 1.0:
            raise ValueError("relative_limit must be at least 1.0")
        if self.case_absolute_tolerance_s < 0.0:
            raise ValueError("case_absolute_tolerance_s must be non-negative")
        if self.total_absolute_tolerance_s < 0.0:
            raise ValueError("total_absolute_tolerance_s must be non-negative")


@dataclass(frozen=True)
class HardwareComparisonResult:
    passed: bool
    report_json: Path
    report_md: Path
    candidate_run_dirs: tuple[Path, ...]
    candidate_bundles: tuple[Path, ...]
    failures: tuple[str, ...]


def _resource_family(resource: str) -> str:
    head = str(resource).strip().split("::", 1)[0].upper()
    return re.sub(r"\d+$", "", head) or head


def _timing_dict(summary: TimingSummary) -> dict[str, Any]:
    return asdict(summary)


def _summary_from_mapping(data: Mapping[str, Any]) -> TimingSummary:
    return TimingSummary(
        minimum=float(data["minimum"]),
        p50=float(data["p50"]),
        p95=float(data["p95"]),
        p99=float(data["p99"]),
        maximum=float(data["maximum"]),
        sample_count=int(data["sample_count"]),
    )


def _load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "results" not in payload:
        raise ValueError(f"Invalid HIL report: {path}")
    return payload


def _fixture_signature(report: Mapping[str, Any]) -> dict[str, Any]:
    config = report.get("config") or {}
    return {
        "suite": str(config.get("suite", "")),
        "channel": int(config.get("channel", 0)),
        "waveform_points": int(config.get("waveform_points", 0)),
        "hardcopy": bool(config.get("hardcopy", False)),
        "expected_frequency_hz": float(config.get("expected_frequency_hz", 0.0)),
        "frequency_tolerance_fraction": float(
            config.get("frequency_tolerance_fraction", 0.0)
        ),
        "min_vpp_v": float(config.get("min_vpp_v", 0.0)),
        "max_vpp_v": float(config.get("max_vpp_v", 0.0)),
    }


def _case_map(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    cases: dict[str, Mapping[str, Any]] = {}
    for raw in report.get("results", []):
        case_id = str(raw.get("case_id", "")).strip()
        if not case_id:
            raise ValueError("HIL report contains a case without case_id")
        if case_id in cases:
            raise ValueError(f"Duplicate HIL case id: {case_id}")
        cases[case_id] = raw
    return cases


def _validate_report_set(reports: Sequence[Mapping[str, Any]]) -> tuple[str, dict[str, str]]:
    if not reports:
        raise ValueError("At least one HIL report is required")
    first = reports[0]
    idn = str(first.get("idn", "")).strip()
    if not idn:
        raise ValueError("HIL report is missing scope IDN")
    signature = _fixture_signature(first)
    first_cases = _case_map(first)
    expected_status = {
        case_id: str(case.get("status", "")) for case_id, case in first_cases.items()
    }
    if any(status == FAIL for status in expected_status.values()):
        raise ValueError("Cannot build/compare a qualified set containing FAIL cases")

    for index, report in enumerate(reports[1:], start=2):
        if str(report.get("idn", "")).strip() != idn:
            raise ValueError(f"HIL repetition {index} used a different scope IDN")
        if _fixture_signature(report) != signature:
            raise ValueError(f"HIL repetition {index} used a different fixture/config")
        cases = _case_map(report)
        statuses = {case_id: str(case.get("status", "")) for case_id, case in cases.items()}
        if statuses != expected_status:
            raise ValueError(
                f"HIL repetition {index} case/status set differs from repetition 1"
            )
    return idn, expected_status


def build_hardware_baseline(
    reports: Sequence[Mapping[str, Any]],
    *,
    resource: str,
) -> dict[str, Any]:
    """Build a portable R0-T baseline from successful repeated HIL reports."""

    idn, expected_status = _validate_report_set(reports)
    first_cases = _case_map(reports[0])
    cases: dict[str, Any] = {}
    for case_id, first_case in first_cases.items():
        samples = [float(_case_map(report)[case_id]["duration_s"]) for report in reports]
        cases[case_id] = {
            "title": str(first_case.get("title", "")),
            "group": str(first_case.get("group", "")),
            "expected_status": expected_status[case_id],
            "timing": _timing_dict(summarize_timings(samples)),
            "slope_s_per_run": linear_slope(samples),
            "samples_s": samples,
        }

    elapsed_samples = [float(report["elapsed_s"]) for report in reports]
    return {
        "schema_version": HARDWARE_BASELINE_SCHEMA_VERSION,
        "kind": "DPO4000 Probe Comp R0 hardware baseline",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "repetitions": len(reports),
        "resource_family": _resource_family(resource),
        "idn": idn,
        "package_version": str(reports[0].get("package_version", "")),
        "platform": str(reports[0].get("platform", "")),
        "fixture": _fixture_signature(reports[0]),
        "expected_counts": dict(reports[0].get("counts") or {}),
        "run_timing": {
            "timing": _timing_dict(summarize_timings(elapsed_samples)),
            "slope_s_per_run": linear_slope(elapsed_samples),
            "samples_s": elapsed_samples,
        },
        "cases": cases,
    }


def compare_hardware_reports(
    baseline: Mapping[str, Any],
    reports: Sequence[Mapping[str, Any]],
    *,
    resource: str,
    relative_limit: float = DEFAULT_RELATIVE_LIMIT,
    case_absolute_tolerance_s: float = DEFAULT_CASE_ABSOLUTE_TOLERANCE_S,
    total_absolute_tolerance_s: float = DEFAULT_TOTAL_ABSOLUTE_TOLERANCE_S,
) -> dict[str, Any]:
    """Compare repeated HIL reports against a reviewed R0 hardware baseline."""

    if int(baseline.get("schema_version", -1)) != HARDWARE_BASELINE_SCHEMA_VERSION:
        raise ValueError("Unsupported hardware baseline schema version")
    idn, candidate_status = _validate_report_set(reports)
    failures: list[str] = []
    warnings: list[str] = []

    if _resource_family(resource) != str(baseline.get("resource_family", "")):
        failures.append(
            "Resource interface family differs: "
            f"baseline={baseline.get('resource_family')} candidate={_resource_family(resource)}"
        )
    if idn != str(baseline.get("idn", "")):
        failures.append("Scope IDN differs from baseline")
    if _fixture_signature(reports[0]) != dict(baseline.get("fixture") or {}):
        failures.append("Probe Comp fixture/config differs from baseline")

    baseline_cases = dict(baseline.get("cases") or {})
    expected_status = {
        case_id: str(case.get("expected_status", ""))
        for case_id, case in baseline_cases.items()
    }
    if candidate_status != expected_status:
        missing = sorted(set(expected_status) - set(candidate_status))
        extra = sorted(set(candidate_status) - set(expected_status))
        changed = sorted(
            case_id
            for case_id in set(expected_status) & set(candidate_status)
            if expected_status[case_id] != candidate_status[case_id]
        )
        failures.append(
            "Functional case/status set differs from baseline: "
            f"missing={missing} extra={extra} changed={changed}"
        )

    case_gate = PerformanceGate(
        relative_limit=relative_limit,
        absolute_tolerance=case_absolute_tolerance_s,
    )
    total_gate = PerformanceGate(
        relative_limit=relative_limit,
        absolute_tolerance=total_absolute_tolerance_s,
    )
    candidate_case_maps = [_case_map(report) for report in reports]
    case_results: dict[str, Any] = {}

    for case_id, baseline_case in baseline_cases.items():
        if case_id not in candidate_status:
            continue
        samples = [float(cases[case_id]["duration_s"]) for cases in candidate_case_maps]
        candidate_summary = summarize_timings(samples)
        baseline_summary = _summary_from_mapping(baseline_case["timing"])
        regressed = False
        if expected_status.get(case_id) == PASS:
            regressed = case_gate.failed(
                baseline=baseline_summary,
                candidate=candidate_summary,
            )
            if regressed:
                failures.append(
                    f"{case_id} p95 regression: baseline={baseline_summary.p95:.3f}s "
                    f"candidate={candidate_summary.p95:.3f}s"
                )
        case_results[case_id] = {
            "status": candidate_status[case_id],
            "baseline": _timing_dict(baseline_summary),
            "candidate": _timing_dict(candidate_summary),
            "delta_p95_s": candidate_summary.p95 - baseline_summary.p95,
            "ratio_p95": (
                candidate_summary.p95 / baseline_summary.p95
                if baseline_summary.p95 > 0.0
                else None
            ),
            "regressed": regressed,
            "candidate_slope_s_per_run": linear_slope(samples),
            "samples_s": samples,
        }

    elapsed_samples = [float(report["elapsed_s"]) for report in reports]
    candidate_total = summarize_timings(elapsed_samples)
    baseline_total = _summary_from_mapping(baseline["run_timing"]["timing"])
    total_regressed = total_gate.failed(baseline=baseline_total, candidate=candidate_total)
    if total_regressed:
        failures.append(
            "Whole-run p95 regression: "
            f"baseline={baseline_total.p95:.3f}s candidate={candidate_total.p95:.3f}s"
        )

    baseline_version = str(baseline.get("package_version", ""))
    candidate_version = str(reports[0].get("package_version", ""))
    if baseline_version and baseline_version != candidate_version:
        warnings.append(
            f"Package version changed: baseline={baseline_version} candidate={candidate_version}"
        )

    return {
        "schema_version": HARDWARE_BASELINE_SCHEMA_VERSION,
        "kind": "DPO4000 Probe Comp R0 hardware comparison",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": PASS if not failures else FAIL,
        "passed": not failures,
        "resource_family": _resource_family(resource),
        "idn": idn,
        "repetitions": len(reports),
        "gates": {
            "relative_limit": float(relative_limit),
            "case_absolute_tolerance_s": float(case_absolute_tolerance_s),
            "total_absolute_tolerance_s": float(total_absolute_tolerance_s),
        },
        "run_timing": {
            "baseline": _timing_dict(baseline_total),
            "candidate": _timing_dict(candidate_total),
            "delta_p95_s": candidate_total.p95 - baseline_total.p95,
            "ratio_p95": (
                candidate_total.p95 / baseline_total.p95
                if baseline_total.p95 > 0.0
                else None
            ),
            "regressed": total_regressed,
            "candidate_slope_s_per_run": linear_slope(elapsed_samples),
            "samples_s": elapsed_samples,
        },
        "cases": case_results,
        "failures": failures,
        "warnings": warnings,
    }


def _hil_config(options: HardwareRegressionOptions) -> HilConfig:
    return HilConfig(
        resource=options.resource,
        output_dir=options.output_dir / "hil_runs",
        channel=options.channel,
        timeout_ms=options.timeout_ms,
        trigger_timeout_s=options.trigger_timeout_s,
        waveform_points=options.waveform_points,
        expected_frequency_hz=options.expected_frequency_hz,
        frequency_tolerance_fraction=options.frequency_tolerance_fraction,
        min_vpp_v=options.min_vpp_v,
        max_vpp_v=options.max_vpp_v,
        hardcopy=options.hardcopy,
        suite=options.suite,
    )


def _run_repetitions(
    options: HardwareRegressionOptions,
    repetitions: int,
) -> tuple[list[dict[str, Any]], list[Path], list[Path]]:
    reports: list[dict[str, Any]] = []
    run_dirs: list[Path] = []
    bundles: list[Path] = []
    for index in range(1, repetitions + 1):
        print(f"\n=== R0 hardware repetition {index}/{repetitions} ===", flush=True)
        runner = AutomationLoggerHilRunner(_hil_config(options))
        exit_code, bundle = runner.run()
        report_path = runner.root / "hil_report.json"
        reports.append(_load_report(report_path))
        run_dirs.append(runner.root)
        bundles.append(bundle)
        if exit_code != 0:
            raise RuntimeError(
                f"HIL repetition {index} failed; inspect diagnostic bundle: {bundle}"
            )
    return reports, run_dirs, bundles


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def _comparison_markdown(payload: Mapping[str, Any], baseline_path: Path) -> str:
    lines = [
        "# DPO4000 Probe Comp R0 Hardware Comparison",
        "",
        f"**Status:** {payload['status']}",
        f"**Baseline:** `{baseline_path}`",
        f"**IDN:** `{payload['idn']}`",
        f"**Repetitions:** {payload['repetitions']}",
        "",
        "| Metric | Baseline p95 | Candidate p95 | Delta | Ratio | Result |",
        "|---|---:|---:|---:|---:|---|",
    ]
    total = payload["run_timing"]
    ratio = total["ratio_p95"]
    lines.append(
        f"| Whole run | {total['baseline']['p95']:.3f}s | "
        f"{total['candidate']['p95']:.3f}s | {total['delta_p95_s']:+.3f}s | "
        f"{ratio:.3f}x | {'FAIL' if total['regressed'] else 'PASS'} |"
    )
    for case_id, case in payload["cases"].items():
        ratio = case["ratio_p95"]
        ratio_text = "--" if ratio is None else f"{ratio:.3f}x"
        lines.append(
            f"| `{case_id}` | {case['baseline']['p95']:.3f}s | "
            f"{case['candidate']['p95']:.3f}s | {case['delta_p95_s']:+.3f}s | "
            f"{ratio_text} | {'FAIL' if case['regressed'] else case['status']} |"
        )
    if payload.get("failures"):
        lines += ["", "## Failures", ""]
        lines.extend(f"- {item}" for item in payload["failures"])
    if payload.get("warnings"):
        lines += ["", "## Warnings", ""]
        lines.extend(f"- {item}" for item in payload["warnings"])
    return "\n".join(lines) + "\n"


def create_hardware_baseline(options: HardwareRegressionOptions) -> Path:
    """Run Probe-Comp HIL repeatedly and write a reviewed-candidate R0 baseline JSON."""

    repetitions = options.repetitions or DEFAULT_BASELINE_REPETITIONS
    reports, run_dirs, bundles = _run_repetitions(options, repetitions)
    payload = build_hardware_baseline(reports, resource=options.resource)
    payload["evidence"] = {
        "run_dirs": [str(path) for path in run_dirs],
        "diagnostic_bundles": [str(path) for path in bundles],
    }
    _write_json(options.baseline_path, payload)
    print(f"\nR0 hardware baseline created: {options.baseline_path}", flush=True)
    return options.baseline_path


def compare_hardware_baseline(options: HardwareRegressionOptions) -> HardwareComparisonResult:
    """Run Probe-Comp HIL repeatedly and compare it to an existing R0 baseline."""

    baseline = json.loads(options.baseline_path.read_text(encoding="utf-8"))
    repetitions = options.repetitions or int(
        baseline.get("repetitions", DEFAULT_BASELINE_REPETITIONS)
    )
    reports, run_dirs, bundles = _run_repetitions(options, repetitions)
    payload = compare_hardware_reports(
        baseline,
        reports,
        resource=options.resource,
        relative_limit=options.relative_limit,
        case_absolute_tolerance_s=options.case_absolute_tolerance_s,
        total_absolute_tolerance_s=options.total_absolute_tolerance_s,
    )
    payload["baseline_path"] = str(options.baseline_path)
    payload["evidence"] = {
        "run_dirs": [str(path) for path in run_dirs],
        "diagnostic_bundles": [str(path) for path in bundles],
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_root = options.output_dir / "comparisons"
    json_path = _write_json(report_root / f"r0_hardware_compare_{stamp}.json", payload)
    md_path = report_root / f"r0_hardware_compare_{stamp}.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(
        _comparison_markdown(payload, options.baseline_path),
        encoding="utf-8",
    )
    failures = tuple(str(item) for item in payload.get("failures", ()))
    print(
        f"\nR0 hardware comparison {'PASS' if payload['passed'] else 'FAIL'}: {json_path}",
        flush=True,
    )
    return HardwareComparisonResult(
        passed=bool(payload["passed"]),
        report_json=json_path,
        report_md=md_path,
        candidate_run_dirs=tuple(run_dirs),
        candidate_bundles=tuple(bundles),
        failures=failures,
    )


__all__ = [
    "DEFAULT_BASELINE_REPETITIONS",
    "DEFAULT_CASE_ABSOLUTE_TOLERANCE_S",
    "DEFAULT_RELATIVE_LIMIT",
    "DEFAULT_TOTAL_ABSOLUTE_TOLERANCE_S",
    "HARDWARE_BASELINE_SCHEMA_VERSION",
    "HardwareComparisonResult",
    "HardwareRegressionOptions",
    "build_hardware_baseline",
    "compare_hardware_baseline",
    "compare_hardware_reports",
    "create_hardware_baseline",
]
