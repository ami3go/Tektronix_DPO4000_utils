#!/usr/bin/env python3
"""Run Automation + Logger HIL using DPO4054 Probe Comp connected to CH1."""
from __future__ import annotations

import argparse
from pathlib import Path

from dpo4000_utils.bench_hil import AutomationLoggerHilRunner, HilConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resource",
        required=True,
        help="VISA resource, e.g. TCPIP0::192.168.0.5::INSTR",
    )
    parser.add_argument(
        "--channel",
        type=int,
        default=1,
        help="Probe Comp input channel (default: 1)",
    )
    parser.add_argument(
        "--suite",
        choices=("all", "automation", "logger"),
        default="all",
    )
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    parser.add_argument("--trigger-timeout-s", type=float, default=10.0)
    parser.add_argument("--waveform-points", type=int, default=1_000)
    parser.add_argument("--expected-frequency-hz", type=float, default=1_000.0)
    parser.add_argument(
        "--frequency-tolerance",
        type=float,
        default=0.35,
        help="Fractional Probe Comp frequency tolerance (default: 0.35 = +/-35%%)",
    )
    parser.add_argument("--min-vpp", type=float, default=0.5)
    parser.add_argument("--max-vpp", type=float, default=5.0)
    parser.add_argument(
        "--skip-hardcopy",
        action="store_true",
        help="Skip image-producing cases A1-A3; useful for faster Logger-only diagnosis",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("hardware_verification_reports") / "automation_logger_hil",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = HilConfig(
        resource=args.resource,
        output_dir=args.output_dir.expanduser().resolve(),
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
    )
    exit_code, bundle = AutomationLoggerHilRunner(config).run()
    print(f"Diagnostic bundle: {bundle}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
