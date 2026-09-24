#!/usr/bin/env python3
"""Capture the R0-F functional and R0-T timing/performance baselines.

See docs/regression-test-plan.md. Both baselines must exist, from a known-good
commit, before A14 (Advanced Trigger) work begins.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dpo4000_utils.baseline_capture import BaselineConfig, HardwareBaselineCapture, build_baseline_header


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource", required=True, help="VISA resource, e.g. TCPIP0::192.168.0.5::INSTR")
    parser.add_argument("--output-dir", type=Path, default=Path("tests/baselines"))
    parser.add_argument("--timeout-ms", type=int, default=20_000)
    parser.add_argument("--test-channel", type=int, choices=(1, 2, 3, 4), default=1)
    parser.add_argument("--reps-standard", type=int, default=20)
    parser.add_argument("--reps-heavy", type=int, default=5)
    parser.add_argument("--reps-waveform-large", type=int, default=2)
    parser.add_argument(
        "--waveform-sizes",
        default="1000,10000,100000,1000000,10000000",
        help="Comma-separated point counts for the waveform-scaling sweep.",
    )
    parser.add_argument("--skip-functional", action="store_true")
    parser.add_argument("--skip-timing", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.timeout_ms <= 0:
        raise SystemExit("--timeout-ms must be positive")
    for name in ("reps_standard", "reps_heavy", "reps_waveform_large"):
        if getattr(args, name) <= 0:
            raise SystemExit(f"--{name.replace('_', '-')} must be positive")
    waveform_sizes = tuple(int(item) for item in args.waveform_sizes.split(","))
    if any(size <= 0 for size in waveform_sizes):
        raise SystemExit("--waveform-sizes entries must be positive")

    config = BaselineConfig(
        resource=args.resource,
        output_dir=args.output_dir,
        timeout_ms=args.timeout_ms,
        test_channel=args.test_channel,
        reps_standard=args.reps_standard,
        reps_heavy=args.reps_heavy,
        reps_waveform_large=args.reps_waveform_large,
        waveform_sizes=waveform_sizes,
    )

    print("DPO4000 R0-F/R0-T baseline capture")
    print(f"  resource: {config.resource}")
    print(f"  output directory: {config.output_dir}")

    capture = HardwareBaselineCapture(config)
    capture.connect()
    try:
        assert capture.scope is not None
        idn = capture.scope.query_identity()
        print(f"  idn: {idn}")

        if not args.skip_functional:
            print("\nCapturing R0-F functional baseline...")
            functional = {**build_baseline_header(config.resource, idn), **capture.capture_functional()}
            functional_path = config.output_dir / "r0_functional_baseline.json"
            functional_path.write_text(json.dumps(functional, indent=2, sort_keys=True), encoding="utf-8")
            print(f"  wrote {functional_path}")

        if not args.skip_timing:
            print("\nCapturing R0-T timing baseline (this touches the scope repeatedly)...")
            timing_data = capture.capture_timing()
            timing = {
                **build_baseline_header(config.resource, idn),
                "transport": config.resource.split("::")[0],
                "operations": timing_data,
            }
            timing_path = config.output_dir / "r0_timing_baseline.json"
            timing_path.write_text(json.dumps(timing, indent=2, sort_keys=True), encoding="utf-8")
            print(f"  wrote {timing_path}")
    finally:
        capture.disconnect()

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
