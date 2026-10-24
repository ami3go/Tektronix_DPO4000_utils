#!/usr/bin/env python3
"""Capture the R0-F functional and R0-T timing/performance baselines.

See docs/regression-test-plan.md. Baseline updates are explicit evidence captures from
known-good hardware; this script never synthesizes or auto-accepts timing values.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from dpo4000_utils.baseline_capture import BaselineConfig, HardwareBaselineCapture, build_baseline_header
from dpo4000_utils.r0_qualification import VerifiedSetupGuard


def _write_new_baseline(destination: Path, payload: dict) -> None:
    """Publish a complete snapshot only when no baseline exists.

    A temporary file is flushed and synced before an exclusive hard-link create.
    Neither ordinary execution nor a race with another capture may replace a
    previously approved reference snapshot.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing baseline: {destination}")
    temp: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temp = Path(handle.name)
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temp, destination)  # exclusive: existing snapshots are never replaced
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource", required=True, help="VISA resource, e.g. TCPIP0::192.168.0.5::INSTR")
    parser.add_argument("--output-dir", type=Path, default=Path("tests/baselines"))
    parser.add_argument("--timeout-ms", type=int, default=20_000)
    parser.add_argument("--expected-idn", required=True,
                        help="Full *IDN? response independently verified before this campaign.")
    parser.add_argument("--confirm-restore-plan", action="store_true",
                        help="Operator verified and approved restoration from saved *LRN?/SET? setup.")
    parser.add_argument(
        "--capability-probe-timeout-ms",
        type=int,
        default=500,
        help="Dedicated bounded VISA timeout used for unsupported A14 capability probes.",
    )
    parser.add_argument("--test-channel", type=int, choices=(1, 2, 3, 4), default=1)
    parser.add_argument("--reps-standard", type=int, default=20)
    parser.add_argument("--reps-heavy", type=int, default=5)
    parser.add_argument("--reps-waveform-large", type=int, default=5)
    parser.add_argument(
        "--waveform-sizes",
        default="1000,10000,100000,1000000,10000000",
        help="Comma-separated point counts for the waveform-scaling sweep.",
    )
    parser.add_argument(
        "--authorize-reversible-writes", action="store_true",
        help="Explicit bench permission: R0 capture configures trigger/channel/acquisition/setup.",
    )
    parser.add_argument("--skip-functional", action="store_true")
    parser.add_argument("--skip-timing", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.authorize_reversible_writes:
        raise SystemExit(
            "R0 capture performs physical configuration writes. "
            "Supply --authorize-reversible-writes only on an approved disposable setup."
        )
    if not args.confirm_restore_plan:
        raise SystemExit("Operator must verify the bench restore plan and pass --confirm-restore-plan")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise SystemExit("Use a new empty output directory for this immutable capture")
    if args.timeout_ms <= 0:
        raise SystemExit("--timeout-ms must be positive")
    if args.capability_probe_timeout_ms <= 0:
        raise SystemExit("--capability-probe-timeout-ms must be positive")
    for name in ("reps_standard", "reps_heavy", "reps_waveform_large"):
        if getattr(args, name) <= 0:
            raise SystemExit(f"--{name.replace('_', '-')} must be positive")
    waveform_sizes = tuple(int(item) for item in args.waveform_sizes.split(","))
    if any(size <= 0 for size in waveform_sizes):
        raise SystemExit("--waveform-sizes entries must be positive")

    # Do this before any physical connection or configuration changes.
    requested_paths = [
        args.output_dir / filename
        for selected, filename in (
            (not args.skip_functional, "r0_functional_baseline.json"),
            (not args.skip_timing, "r0_timing_baseline.json"),
        )
        if selected
    ]
    if not requested_paths:
        raise SystemExit("At least one baseline type must be selected")
    for path in requested_paths:
        if path.exists():
            raise SystemExit(f"Baseline already exists; no overwrite permitted: {path}")

    config = BaselineConfig(
        resource=args.resource,
        output_dir=args.output_dir,
        timeout_ms=args.timeout_ms,
        capability_probe_timeout_ms=args.capability_probe_timeout_ms,
        test_channel=args.test_channel,
        reps_standard=args.reps_standard,
        reps_heavy=args.reps_heavy,
        reps_waveform_large=args.reps_waveform_large,
        waveform_sizes=waveform_sizes,
    )

    print("DPO4000 R0-F/R0-T baseline capture")
    print(f"  resource: {config.resource}")
    print(f"  output directory: {config.output_dir}")
    print(f"  A14 capability probe timeout: {config.capability_probe_timeout_ms} ms")

    capture = HardwareBaselineCapture(config)
    results: list[tuple[Path, dict]] = []
    capture.connect()
    try:
        with VerifiedSetupGuard(capture, config.output_dir, args.expected_idn) as guard:
            idn = guard.expected_idn
            print(f"  verified idn: {idn}")
            if not args.skip_functional:
                print("\nCapturing R0-F functional baseline...")
                functional = {**build_baseline_header(config.resource, idn), **capture.capture_functional()}
                results.append((config.output_dir / "r0_functional_baseline.json", functional))
            if not args.skip_timing:
                print("\nCapturing R0-T timing baseline (this touches the scope repeatedly)...")
                timing_data = capture.capture_timing()
                timing = {
                    **build_baseline_header(config.resource, idn),
                    "transport": config.resource.split("::")[0],
                    "operations": timing_data,
                }
                results.append((config.output_dir / "r0_timing_baseline.json", timing))
        # Only publish after the physical setup was verified restored.
        for _, document in results:
            document["setup_restoration"] = dict(guard.report)
    finally:
        capture.disconnect()

    # Do not leave a seemingly approved functional baseline behind if the
    # hardware timing capture failed. Publish only after both stages complete.
    for path, payload in results:
        _write_new_baseline(path, payload)
        print(f"  wrote {path}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
