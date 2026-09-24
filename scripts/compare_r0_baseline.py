#!/usr/bin/env python3
"""Compare a candidate R0-F/R0-T capture against the committed baseline.

See docs/regression-test-plan.md sections 4.4 and 16. Never writes to --baseline-dir;
updating the baseline stays a separate, explicit scripts/capture_r0_baseline.py run.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from dpo4000_utils.baseline_capture import BaselineConfig, HardwareBaselineCapture, build_baseline_header
from dpo4000_utils.baseline_compare import (
    diff_functional,
    diff_timing,
    load_thresholds,
    regression_exit_code,
)


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
        "--candidate-timing",
        type=Path,
        help="Path to an already-captured timing JSON (required with --candidate-functional).",
    )

    parser.add_argument("--timeout-ms", type=int, default=20_000)
    parser.add_argument("--test-channel", type=int, choices=(1, 2, 3, 4), default=1)
    parser.add_argument("--reps-standard", type=int, default=20)
    parser.add_argument("--reps-heavy", type=int, default=5)
    parser.add_argument("--reps-waveform-large", type=int, default=2)
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
    config = BaselineConfig(
        resource=args.resource,
        output_dir=output_dir,
        timeout_ms=args.timeout_ms,
        test_channel=args.test_channel,
        reps_standard=args.reps_standard,
        reps_heavy=args.reps_heavy,
        reps_waveform_large=args.reps_waveform_large,
        waveform_sizes=waveform_sizes,
    )
    capture = HardwareBaselineCapture(config)
    capture.connect()
    try:
        assert capture.scope is not None
        idn = capture.scope.query_identity()
        print(f"  idn: {idn}")
        functional = {**build_baseline_header(config.resource, idn), **capture.capture_functional()}
        timing_data = capture.capture_timing()
        timing = {
            **build_baseline_header(config.resource, idn),
            "transport": config.resource.split("::")[0],
            "operations": timing_data,
        }
    finally:
        capture.disconnect()
    return functional, timing


def main() -> int:
    args = build_parser().parse_args()
    if args.candidate_functional and not args.candidate_timing:
        raise SystemExit("--candidate-timing is required when --candidate-functional is given")

    output_dir = args.output_dir or default_output_dir()
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
        print(f"  candidate: live capture against {args.resource}")
        candidate_functional, candidate_timing = _capture_candidate_live(args, output_dir)
    else:
        print(f"  candidate: {args.candidate_functional}, {args.candidate_timing}")
        candidate_functional, candidate_timing = _load_candidate_from_files(
            args.candidate_functional, args.candidate_timing
        )

    functional_diffs = diff_functional(baseline_functional, candidate_functional)
    timing_regressions, new_operations, missing_operations = diff_timing(
        baseline_timing.get("operations", {}),
        candidate_timing.get("operations", {}),
        thresholds,
    )
    regressed = [r for r in timing_regressions if r.regressed]

    report = {
        "baseline_dir": str(args.baseline_dir),
        "thresholds_file": str(args.thresholds),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "functional_diffs": [asdict(d) for d in functional_diffs],
        "timing_regressions": [asdict(r) for r in timing_regressions],
        "new_operations": new_operations,
        "missing_operations": missing_operations,
    }
    report_path = output_dir / "comparison_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")

    print("\nComparison summary")
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
        print(f"  missing operations (baseline only, informational): {missing_operations}")
    print(f"  report: {report_path}")

    return regression_exit_code(functional_diffs, timing_regressions)


if __name__ == "__main__":
    raise SystemExit(main())
