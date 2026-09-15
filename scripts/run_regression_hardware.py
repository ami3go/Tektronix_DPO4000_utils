#!/usr/bin/env python3
"""Create or compare the DPO4000 Probe-Comp R0 hardware performance baseline."""

from __future__ import annotations

import argparse
from pathlib import Path

from dpo4000_utils.hardware_regression import (
    DEFAULT_BASELINE_REPETITIONS,
    DEFAULT_CASE_ABSOLUTE_TOLERANCE_S,
    DEFAULT_RELATIVE_LIMIT,
    DEFAULT_TOTAL_ABSOLUTE_TOLERANCE_S,
    HardwareRegressionOptions,
    compare_hardware_baseline,
    create_hardware_baseline,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--create-baseline",
        action="store_true",
        help="Run repeated Probe-Comp HIL and write a new baseline JSON.",
    )
    mode.add_argument(
        "--compare-baseline",
        action="store_true",
        help="Run repeated Probe-Comp HIL and compare it with an existing baseline.",
    )
    parser.add_argument(
        "--resource",
        required=True,
        help="VISA resource, e.g. TCPIP0::192.168.0.5::INSTR",
    )
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument("--suite", choices=("all", "automation", "logger"), default="all")
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    parser.add_argument("--trigger-timeout-s", type=float, default=10.0)
    parser.add_argument("--waveform-points", type=int, default=1_000)
    parser.add_argument("--expected-frequency-hz", type=float, default=1_000.0)
    parser.add_argument("--frequency-tolerance", type=float, default=0.35)
    parser.add_argument("--min-vpp", type=float, default=0.5)
    parser.add_argument("--max-vpp", type=float, default=5.0)
    parser.add_argument(
        "--skip-hardcopy",
        action="store_true",
        help="Exclude A1-A3 image cases; baseline/compare must use the same setting.",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=None,
        help=(
            f"Number of complete HIL repetitions. Create defaults to {DEFAULT_BASELINE_REPETITIONS}; "
            "compare defaults to the baseline repetition count."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("hardware_verification_reports") / "r0_probe_comp",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Baseline JSON path. Default: <output-dir>/r0_hardware_baseline.json",
    )
    parser.add_argument(
        "--force-baseline",
        action="store_true",
        help="Allow --create-baseline to replace an existing reviewed baseline.",
    )
    parser.add_argument(
        "--relative-limit",
        type=float,
        default=DEFAULT_RELATIVE_LIMIT,
        help="p95 relative regression limit (default: 1.30 = +30%%).",
    )
    parser.add_argument(
        "--case-absolute-tolerance-s",
        type=float,
        default=DEFAULT_CASE_ABSOLUTE_TOLERANCE_S,
        help="Per-case absolute p95 tolerance in seconds (default: 0.25).",
    )
    parser.add_argument(
        "--total-absolute-tolerance-s",
        type=float,
        default=DEFAULT_TOTAL_ABSOLUTE_TOLERANCE_S,
        help="Whole-run absolute p95 tolerance in seconds (default: 2.0).",
    )
    return parser.parse_args()


def _options(args: argparse.Namespace) -> HardwareRegressionOptions:
    output_dir = args.output_dir.expanduser().resolve()
    baseline_path = (
        args.baseline.expanduser().resolve()
        if args.baseline is not None
        else output_dir / "r0_hardware_baseline.json"
    )
    return HardwareRegressionOptions(
        resource=args.resource,
        output_dir=output_dir,
        baseline_path=baseline_path,
        repetitions=args.repetitions,
        channel=args.channel,
        timeout_ms=args.timeout_ms,
        trigger_timeout_s=args.trigger_timeout_s,
        waveform_points=args.waveform_points,
        expected_frequency_hz=args.expected_frequency_hz,
        frequency_tolerance_fraction=args.frequency_tolerance,
        min_vpp_v=args.min_vpp,
        max_vpp_v=args.max_vpp,
        hardcopy=not args.skip_hardcopy,
        suite=args.suite,
        relative_limit=args.relative_limit,
        case_absolute_tolerance_s=args.case_absolute_tolerance_s,
        total_absolute_tolerance_s=args.total_absolute_tolerance_s,
    )


def main() -> int:
    args = parse_args()
    options = _options(args)
    if args.create_baseline:
        if options.baseline_path.exists() and not args.force_baseline:
            raise SystemExit(
                "Baseline already exists: "
                f"{options.baseline_path}\n"
                "Refusing to overwrite a reviewed baseline. "
                "Use --force-baseline only when intentionally replacing it."
            )
        create_hardware_baseline(options)
        return 0
    if not options.baseline_path.is_file():
        raise SystemExit(f"Baseline does not exist: {options.baseline_path}")
    result = compare_hardware_baseline(options)
    if result.failures:
        print("Failures:")
        for failure in result.failures:
            print(f"  - {failure}")
    print(f"Comparison JSON: {result.report_json}")
    print(f"Comparison Markdown: {result.report_md}")
    print("Candidate diagnostic bundles:")
    for bundle in result.candidate_bundles:
        print(f"  - {bundle}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
