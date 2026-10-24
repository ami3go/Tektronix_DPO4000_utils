#!/usr/bin/env python3
"""Compare a candidate R0-F/R0-T capture against the committed baseline.

See docs/regression-test-plan.md sections 4.4 and 16. Never writes to --baseline-dir;
updating the baseline stays a separate, explicit scripts/capture_r0_baseline.py run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import math
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from dpo4000_utils.baseline_capture import BaselineConfig, HardwareBaselineCapture, build_baseline_header
from dpo4000_utils.r0_qualification import VerifiedSetupGuard
from dpo4000_utils.baseline_compare import (
    diff_functional,
    diff_timing,
    load_thresholds,
)


def _atomic_json(destination: Path, payload: dict) -> str:
    """Durably publish raw observations/report and return SHA-256 of bytes."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    temp: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="wb", dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temp = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, destination)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    return hashlib.sha256(data).hexdigest()


def default_output_dir() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("regression_reports") / timestamp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, default=Path("tests/baselines"))
    parser.add_argument(
        "--thresholds", type=Path, default=Path("tests/baselines/r0_timing_thresholds.json")
    )
    parser.add_argument("--output-dir", type=Path, default=None)

    candidate = parser.add_mutually_exclusive_group(required=True)
    candidate.add_argument("--resource", help="VISA resource to capture a fresh candidate from.")
    candidate.add_argument(
        "--candidate-functional",
        type=Path,
        help="Path to an already-captured functional JSON (use with --candidate-timing).",
    )

    parser.add_argument(
        "--authorize-reversible-writes", action="store_true",
        help="Required for --resource: live R0 comparison changes and restores scope setup.",
    )
    parser.add_argument(
        "--candidate-timing",
        type=Path,
        help="Path to an already-captured timing JSON (required with --candidate-functional).",
    )

    parser.add_argument("--timeout-ms", type=int, default=20_000)
    parser.add_argument("--expected-idn",
                        help="Exact *IDN? independently verified before any live configuration writes.")
    parser.add_argument("--confirm-restore-plan", action="store_true",
                        help="Operator verified the restoration procedure and approved its use.")
    parser.add_argument(
        "--capability-probe-timeout-ms",
        type=int,
        default=500,
        help="Dedicated bounded timeout used by live A14 unsupported-capability probes.",
    )
    parser.add_argument("--test-channel", type=int, choices=(1, 2, 3, 4), default=1)
    parser.add_argument("--reps-standard", type=int, default=20)
    parser.add_argument("--reps-heavy", type=int, default=5)
    parser.add_argument("--reps-waveform-large", type=int, default=5)
    parser.add_argument(
        "--waveform-sizes",
        default="1000,10000,100000,1000000,10000000",
        help="Comma-separated point counts for the waveform-scaling sweep (--resource mode only).",
    )
    return parser


def _load_candidate_from_files(functional_path: Path, timing_path: Path) -> tuple[dict, dict]:
    functional = json.loads(functional_path.read_text(encoding="utf-8"))
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    return functional, timing


def _capture_candidate_live(args: argparse.Namespace, output_dir: Path) -> tuple[dict, dict]:
    waveform_sizes = tuple(int(item) for item in args.waveform_sizes.split(","))
    if not waveform_sizes or any(size <= 0 for size in waveform_sizes):
        raise ValueError("Waveform sizes must be positive")
    config = BaselineConfig(
        resource=args.resource,
        output_dir=output_dir,
        timeout_ms=args.timeout_ms,
        capability_probe_timeout_ms=args.capability_probe_timeout_ms,
        test_channel=args.test_channel,
        reps_standard=args.reps_standard,
        reps_heavy=args.reps_heavy,
        reps_waveform_large=args.reps_waveform_large,
        waveform_sizes=waveform_sizes,
    )
    capture = HardwareBaselineCapture(config)
    capture.connect()
    try:
        with VerifiedSetupGuard(capture, output_dir, args.expected_idn) as guard:
            idn = guard.expected_idn
            print(f"  verified idn: {idn}")
            functional = {**build_baseline_header(config.resource, idn), **capture.capture_functional()}
            timing_data = capture.capture_timing()
            timing = {
                **build_baseline_header(config.resource, idn),
                "transport": config.resource.split("::")[0],
                "operations": timing_data,
            }
        functional["setup_restoration"] = dict(guard.report)
        timing["setup_restoration"] = dict(guard.report)
    finally:
        capture.disconnect()
    return functional, timing

def _resource_family(document: dict) -> str:
    resource = str(document.get("resource") or "")
    return resource.split("::", 1)[0].upper()


def _operation_names(operations: dict) -> set[str]:
    names: set[str] = set()
    for name, value in operations.items():
        if name == "not_yet_covered":
            continue
        if name == "waveform_acquisition" and isinstance(value, dict):
            names.update(
                f"waveform_acquisition.{size}" for size, stats in value.items()
                if isinstance(stats, dict) and "p95" in stats
            )
        elif isinstance(value, dict) and "p95" in value:
            names.add(name)
    return names


def _identity_differences(
    baseline_functional: dict,
    baseline_timing: dict,
    candidate_functional: dict,
    candidate_timing: dict,
) -> list[str]:
    """Reject cross-transport/cross-instrument baseline comparisons."""
    issues: list[str] = []
    documents = {
        "baseline functional": baseline_functional,
        "baseline timing": baseline_timing,
        "candidate functional": candidate_functional,
        "candidate timing": candidate_timing,
    }
    transports = {name: _resource_family(doc) for name, doc in documents.items()}
    if not all(value and (value.startswith("USB") or value.startswith("TCPIP"))
               for value in transports.values()):
        issues.append(f"Missing or unsupported VISA transport metadata: {transports}")
    elif len(set(transports.values())) != 1:
        issues.append(f"Transport mismatch: {transports}")
    idns = {name: doc.get("idn") for name, doc in documents.items()}
    if not all(isinstance(value, str) and value.strip() for value in idns.values()):
        issues.append(f"Missing scope identity: {idns}")
    elif len(set(idns.values())) != 1:
        issues.append(f"Scope identity mismatch: {idns}")
    return issues


def _timing_quality_issues(operations: dict, label: str) -> list[str]:
    """Refuse malformed distributions and discarded raw duration observations."""
    issues: list[str] = []
    if not isinstance(operations, dict):
        return [f"{label}: timing operations must be an object"]
    stats_by_name: dict[str, dict] = {}
    for name, value in operations.items():
        if name == "not_yet_covered":
            continue
        if name == "waveform_acquisition" and isinstance(value, dict):
            stats_by_name.update({f"{name}.{size}": record for size, record in value.items()})
        else:
            stats_by_name[name] = value
    for name, value in stats_by_name.items():
        if not isinstance(value, dict):
            issues.append(f"{label}: malformed operation {name}")
            continue
        samples = value.get("samples_s")
        count = value.get("sample_count")
        if not isinstance(samples, list) or not samples or type(count) is not int or count != len(samples):
            issues.append(f"{label}: missing/mismatched raw timing observations for {name}")
            continue
        if any(not isinstance(x, (int, float)) or isinstance(x, bool) or
               not math.isfinite(x) or x < 0 for x in samples):
            issues.append(f"{label}: invalid raw timing sample in {name}")
            continue
        for metric in ("min", "p50", "p95", "max"):
            v = value.get(metric)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v < 0:
                issues.append(f"{label}: invalid {metric} in {name}")
    for size in (1000, 10000, 100000, 1000000):
        if f"waveform_acquisition.{size}" not in stats_by_name:
            issues.append(f"{label}: required waveform size {size} not measured")
    return issues


def _restoration_issues(*documents: dict) -> list[str]:
    return [
        f"Document {index}: missing or unverified setup-restoration evidence"
        for index, document in enumerate(documents, start=1)
        if not isinstance(document.get("setup_restoration"), dict)
        or document["setup_restoration"].get("status") != "VERIFIED"
        or document["setup_restoration"].get("verified") is not True
    ]


def main() -> int:
    args = build_parser().parse_args()
    if args.resource and (not args.expected_idn or not args.confirm_restore_plan):
        raise SystemExit(
            "Live R0 needs --expected-idn and --confirm-restore-plan before physical writes"
        )
    if args.resource and not args.authorize_reversible_writes:
        raise SystemExit(
            "Live R0 comparison issues physical configuration writes; "
            "explicit --authorize-reversible-writes is mandatory."
        )
    if args.candidate_functional and not args.candidate_timing:
        raise SystemExit("--candidate-timing is required when --candidate-functional is given")
    if args.timeout_ms <= 0:
        raise SystemExit("--timeout-ms must be positive")
    if args.capability_probe_timeout_ms <= 0:
        raise SystemExit("--capability-probe-timeout-ms must be positive")

    output_dir = args.output_dir or default_output_dir()
    if output_dir.resolve().is_relative_to(args.baseline_dir.resolve()):
        raise SystemExit("Candidate output must not lie within the approved baseline directory")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise SystemExit("Use a new empty output directory to retain immutable candidate evidence")
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_functional = json.loads(
        (args.baseline_dir / "r0_functional_baseline.json").read_text(encoding="utf-8")
    )
    baseline_timing = json.loads(
        (args.baseline_dir / "r0_timing_baseline.json").read_text(encoding="utf-8")
    )
    thresholds = load_thresholds(json.loads(args.thresholds.read_text(encoding="utf-8")))

    print("DPO4000 R0-F/R0-T baseline comparison")
    print(f"  baseline directory: {args.baseline_dir}")
    print(f"  thresholds: {args.thresholds}")
    print(f"  output directory: {output_dir}")

    if args.resource:
        if args.expected_idn != baseline_functional.get("idn"):
            raise SystemExit("Preflight expected IDN differs from approved baseline identity")
        print(f"  candidate: live capture against {args.resource}")
        candidate_functional, candidate_timing = _capture_candidate_live(args, output_dir)
    else:
        print(f"  candidate: {args.candidate_functional}, {args.candidate_timing}")
        candidate_functional, candidate_timing = _load_candidate_from_files(
            args.candidate_functional, args.candidate_timing
        )

    # Retain the actual raw candidate R0-F/R0-T samples for independent audit
    # before reducing them into comparisons. Never overwrite approved baselines.
    functional_candidate_path = output_dir / "r0_candidate_functional.json"
    timing_candidate_path = output_dir / "r0_candidate_timing.json"
    functional_candidate_hash = _atomic_json(functional_candidate_path, candidate_functional)
    timing_candidate_hash = _atomic_json(timing_candidate_path, candidate_timing)

    identity_issues = _identity_differences(
        baseline_functional, baseline_timing, candidate_functional, candidate_timing
    )
    restoration_issues = _restoration_issues(
        baseline_functional, baseline_timing, candidate_functional, candidate_timing
    )
    timing_quality_issues = (
        _timing_quality_issues(baseline_timing.get("operations"), "baseline")
        + _timing_quality_issues(candidate_timing.get("operations"), "candidate")
    )
    functional_diffs = diff_functional(baseline_functional, candidate_functional)
    timing_regressions, new_operations, missing_operations = diff_timing(
        baseline_timing.get("operations", {}),
        candidate_timing.get("operations", {}),
        thresholds,
    )
    regressed = [r for r in timing_regressions if r.regressed]
    # Never report success for operations silently omitted by a threshold file.
    baseline_ops = baseline_timing.get("operations", {})
    candidate_ops = candidate_timing.get("operations", {})
    compared_names = {entry.operation for entry in timing_regressions}
    unthresholded_operations = sorted(
        (_operation_names(baseline_ops) & _operation_names(candidate_ops))
        - compared_names
    )
    missing_coverage = sorted(
        set(baseline_ops.get("not_yet_covered", []))
        | set(candidate_ops.get("not_yet_covered", []))
    )
    unmeasured_thresholds = sorted(
        set(thresholds) - (_operation_names(baseline_ops) & _operation_names(candidate_ops))
    )

    report = {
        "status": "NOT_EVALUATED",
        "candidate_functional_sha256": functional_candidate_hash,
        "candidate_timing_sha256": timing_candidate_hash,
        "identity_issues": identity_issues,
        "restoration_issues": restoration_issues,
        "timing_quality_issues": timing_quality_issues,
        "unmeasured_thresholds": unmeasured_thresholds,
        "thresholds_sha256": hashlib.sha256(args.thresholds.read_bytes()).hexdigest(),
        "unthresholded_operations": unthresholded_operations,
        "known_coverage_gaps": missing_coverage,
        "baseline_dir": str(args.baseline_dir),
        "thresholds_file": str(args.thresholds),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "functional_diffs": [asdict(d) for d in functional_diffs],
        "timing_regressions": [asdict(r) for r in timing_regressions],
        "new_operations": new_operations,
        "missing_operations": missing_operations,
    }
    exit_code = int(bool(
        identity_issues or restoration_issues or timing_quality_issues
        or unmeasured_thresholds or missing_operations or functional_diffs
        or unthresholded_operations or missing_coverage
        or any(result.regressed for result in timing_regressions)
    ))
    report["status"] = "FAIL" if exit_code else "PASS"
    report["failure_reasons"] = (
        identity_issues + restoration_issues + timing_quality_issues
        + ([f"Unmeasured threshold operations: {unmeasured_thresholds}"]
           if unmeasured_thresholds else [])
        + ([f"Missing candidate timing operations: {missing_operations}"] if missing_operations else [])
        + ([f"Unthresholded timing operations: {unthresholded_operations}"]
           if unthresholded_operations else [])
        + ([f"Unqualified timing coverage: {missing_coverage}"]
           if missing_coverage else [])
    )
    report_path = output_dir / "comparison_report.json"
    _atomic_json(report_path, report)

    print("\nComparison summary")
    print(f"  identity/transport issues: {identity_issues}")
    print(f"  setup restoration issues: {restoration_issues}")
    print(f"  timing observation integrity issues: {timing_quality_issues}")
    print(f"  unmeasured threshold operations: {unmeasured_thresholds}")
    print(f"  timing metrics lacking acceptance thresholds: {unthresholded_operations}")
    print(f"  remaining coverage gaps: {missing_coverage}")
    print(f"  functional diffs: {len(functional_diffs)}")
    for diff in functional_diffs:
        print(f"    [{diff.kind}] {diff.path}: baseline={diff.baseline!r} candidate={diff.candidate!r}")
    print(f"  timing operations compared: {len(timing_regressions)}")
    print(f"  timing regressions: {len(regressed)}")
    for r in regressed:
        print(
            f"    {r.operation}: baseline {r.metric}={r.baseline_value:.6g}s "
            f"candidate={r.candidate_value:.6g}s "
            f"(limit {r.relative_limit}x, absolute tolerance {r.absolute_tolerance_s}s)"
        )
    if new_operations:
        print(f"  new operations (candidate only, informational): {new_operations}")
    if missing_operations:
        print(f"  missing operations (FAIL): {missing_operations}")
    print(f"  raw candidate functional: {functional_candidate_path}")
    print(f"  raw candidate timing: {timing_candidate_path}")
    print(f"  report: {report_path}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
