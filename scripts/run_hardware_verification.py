#!/usr/bin/env python3
"""Run full DPO4000 public-API verification against connected real hardware."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from dpo4000_utils.hardware_verification import (
    HardwareVerifier,
    VerificationConfig,
    VerificationRisk,
)


PROFILE_MAP = {
    "read-only": VerificationRisk.READ_ONLY,
    "reversible": VerificationRisk.REVERSIBLE,
    "full": VerificationRisk.DISRUPTIVE,
}


def default_output_dir() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("hardware_verification_reports") / timestamp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the public dpo4000-utils hardware API on a connected DPO4000-family "
            "oscilloscope and generate Markdown, HTML, and JSON evidence reports."
        )
    )
    parser.add_argument(
        "--resource",
        required=True,
        help="VISA resource, for example USB0::0x0699::0x0401::C011280::INSTR",
    )
    parser.add_argument(
        "--profile",
        choices=tuple(PROFILE_MAP),
        default="read-only",
        help=(
            "read-only performs no intentional scope configuration writes; reversible adds "
            "temporary writes followed by setup restoration; full also exercises disruptive "
            "acquisition/trigger/settings operations."
        ),
    )
    parser.add_argument("--timeout-ms", type=int, default=20_000)
    parser.add_argument("--test-channel", type=int, choices=(1, 2, 3, 4), default=1)
    parser.add_argument(
        "--waveform-points",
        type=int,
        default=1_000,
        help="Point count used by structured binary waveform verification.",
    )
    parser.add_argument(
        "--artifact-record-length",
        type=int,
        default=1_000,
        help=(
            "Temporary target record length for legacy CSV evidence. The runner never increases "
            "the current record length for this check."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Report/evidence directory. Default: hardware_verification_reports/<UTC timestamp>.",
    )
    parser.add_argument(
        "--allow-reference-overwrite",
        action="store_true",
        help=(
            "Permit the full profile to overwrite one REF waveform while testing "
            "save_waveform_to_reference(). This content may not be recoverable from *LRN?."
        ),
    )
    parser.add_argument(
        "--reference-destination",
        type=int,
        choices=(1, 2, 3, 4),
        default=4,
        help="Disposable REF slot used only with --allow-reference-overwrite (default: 4).",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.timeout_ms <= 0:
        raise SystemExit("--timeout-ms must be positive")
    if args.waveform_points <= 0:
        raise SystemExit("--waveform-points must be positive")
    if args.artifact_record_length <= 0:
        raise SystemExit("--artifact-record-length must be positive")

    output_dir = args.output_dir or default_output_dir()
    config = VerificationConfig(
        resource=args.resource,
        output_dir=output_dir,
        profile=PROFILE_MAP[args.profile],
        timeout_ms=args.timeout_ms,
        test_channel=args.test_channel,
        waveform_points=args.waveform_points,
        artifact_record_length=args.artifact_record_length,
        allow_reference_overwrite=args.allow_reference_overwrite,
        reference_destination=args.reference_destination,
    )

    print("DPO4000 real-hardware verification")
    print(f"  resource: {config.resource}")
    print(f"  profile: {args.profile}")
    print(f"  test channel: CH{config.test_channel}")
    print(f"  waveform points: {config.waveform_points}")
    print(f"  evidence directory: {config.output_dir}")
    if args.profile == "full":
        print(
            "  reference overwrite: "
            + (
                f"ENABLED -> REF{config.reference_destination}"
                if config.allow_reference_overwrite
                else "disabled (save_waveform_to_reference will be reported SKIP)"
            )
        )

    verifier = HardwareVerifier(config)
    report = verifier.run()

    print("\nVerification summary")
    print(
        f"  cases: PASS={report['totals']['PASS']} "
        f"FAIL={report['totals']['FAIL']} SKIP={report['totals']['SKIP']}"
    )
    print(
        "  public methods: "
        f"{report['api_totals']['methods_pass']}/{report['api_totals']['methods_total']} passed"
    )
    print(
        "  public functions: "
        f"{report['api_totals']['functions_pass']}/{report['api_totals']['functions_total']} passed"
    )
    print(f"  unverified public symbols: {report['api_totals']['unverified']}")
    print(f"  Markdown: {config.output_dir / 'verification_report.md'}")
    print(f"  HTML:     {config.output_dir / 'verification_report.html'}")
    print(f"  JSON:     {config.output_dir / 'verification_report.json'}")

    exit_code = verifier.exit_code(report)
    if exit_code == 2:
        print(
            "\nFull profile did not exercise save_waveform_to_reference(). "
            "Choose a disposable REF slot and re-run with --allow-reference-overwrite "
            "to obtain 100% destructive-method coverage."
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
