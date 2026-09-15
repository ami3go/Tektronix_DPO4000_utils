#!/usr/bin/env python3
"""Capture the R0-F functional and R0-T timing/performance baselines.

See docs/regression-test-plan.md. Both baselines must exist, from a known-good
commit, before A14 (Advanced Trigger) work begins.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from dpo4000_utils.baseline_capture import BaselineConfig, HardwareBaselineCapture


def _package_version() -> str:
    try:
        return metadata.version("dpo4000-utils")
    except metadata.PackageNotFoundError:
        return "source-tree"


def _commit_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def _firmware_from_idn(idn: str) -> str:
    for token in idn.split():
        if token.upper().startswith("FV:"):
            return token[3:]
    return ""


def _header(resource: str, idn: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "commit_sha": _commit_sha(),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "package_version": _package_version(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "resource": resource,
        "idn": idn,
        "firmware": _firmware_from_idn(idn),
    }


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
            functional = {**_header(config.resource, idn), **capture.capture_functional()}
            functional_path = config.output_dir / "r0_functional_baseline.json"
            functional_path.write_text(json.dumps(functional, indent=2, sort_keys=True), encoding="utf-8")
            print(f"  wrote {functional_path}")

        if not args.skip_timing:
            print("\nCapturing R0-T timing baseline (this touches the scope repeatedly)...")
            timing_data = capture.capture_timing()
            timing = {
                **_header(config.resource, idn),
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
