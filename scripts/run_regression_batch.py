#!/usr/bin/env python3
"""Orchestrate the complete DPO4000 regression campaign.

Runs the software R0 regression tests first, then optionally runs the real
DPO4000 Probe-Comp hardware regression in create- or compare-baseline mode.
The script returns a non-zero exit code if any requested stage fails.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("hardware_verification_reports") / "r0_probe_comp"
EXTRA_REGRESSION_TESTS = (
    Path("tests/test_hardware_regression.py"),
    Path("tests/test_persistent_scope_stress.py"),
    Path("tests/test_logger_stress.py"),
)


@dataclass(frozen=True)
class StageResult:
    name: str
    status: str
    return_code: int
    duration_s: float
    command: tuple[str, ...]


def discover_regression_tests(repo_root: Path = REPO_ROOT) -> list[Path]:
    """Return the complete software regression test set in stable order."""

    tests_dir = repo_root / "tests"
    discovered = sorted(tests_dir.glob("test_regression_*.py"))
    for relative in EXTRA_REGRESSION_TESTS:
        path = repo_root / relative
        if path.is_file() and path not in discovered:
            discovered.append(path)
    return discovered


def _relative_strings(paths: Sequence[Path]) -> list[str]:
    return [str(path.relative_to(REPO_ROOT)) for path in paths]


def build_software_command(*, all_tests: bool = False) -> list[str]:
    targets = ["tests"] if all_tests else _relative_strings(discover_regression_tests())
    return [sys.executable, "-m", "pytest", "-q", *targets]


def build_hardware_command(args: argparse.Namespace) -> list[str]:
    if args.hardware == "skip":
        return []
    if not args.resource:
        raise ValueError("--resource is required when --hardware=create or compare")

    output_dir = Path(args.output_dir)
    baseline = Path(args.baseline) if args.baseline else output_dir / "r0_hardware_baseline.json"
    command = [
        sys.executable,
        "scripts/run_regression_hardware.py",
        "--create-baseline" if args.hardware == "create" else "--compare-baseline",
        "--resource",
        args.resource,
        "--channel",
        str(args.channel),
        "--suite",
        args.suite,
        "--waveform-points",
        str(args.waveform_points),
        "--output-dir",
        str(output_dir),
        "--baseline",
        str(baseline),
        "--relative-limit",
        str(args.relative_limit),
        "--case-absolute-tolerance-s",
        str(args.case_absolute_tolerance_s),
        "--total-absolute-tolerance-s",
        str(args.total_absolute_tolerance_s),
    ]
    if args.repetitions is not None:
        command += ["--repetitions", str(args.repetitions)]
    if args.skip_hardcopy:
        command.append("--skip-hardcopy")
    if args.hardware == "create" and args.force_baseline:
        command.append("--force-baseline")
    return command


def _run_stage(name: str, command: Sequence[str]) -> StageResult:
    print(f"\n=== {name} ===", flush=True)
    print("Command:", subprocess.list2cmdline(list(command)), flush=True)
    started = time.perf_counter()
    completed = subprocess.run(list(command), cwd=REPO_ROOT, check=False)
    duration = time.perf_counter() - started
    status = "PASS" if completed.returncode == 0 else "FAIL"
    print(f"{name}: {status} ({duration:.2f}s)", flush=True)
    return StageResult(
        name=name,
        status=status,
        return_code=int(completed.returncode),
        duration_s=duration,
        command=tuple(str(item) for item in command),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hardware",
        choices=("skip", "create", "compare"),
        default="skip",
        help="Hardware stage: skip, create baseline, or compare to baseline.",
    )
    parser.add_argument(
        "--resource",
        help="VISA resource for hardware stage, e.g. TCPIP0::192.168.0.5::INSTR",
    )
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument("--suite", choices=("all", "automation", "logger"), default="all")
    parser.add_argument("--waveform-points", type=int, default=1_000)
    parser.add_argument("--repetitions", type=int, default=None)
    parser.add_argument("--skip-hardcopy", action="store_true")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--relative-limit", type=float, default=1.30)
    parser.add_argument("--case-absolute-tolerance-s", type=float, default=0.25)
    parser.add_argument("--total-absolute-tolerance-s", type=float, default=2.0)
    parser.add_argument(
        "--all-tests",
        action="store_true",
        help="Run the entire pytest suite instead of only regression/stress tests.",
    )
    parser.add_argument(
        "--continue-after-software-failure",
        action="store_true",
        help="Still run hardware even if the software regression stage fails.",
    )
    parser.add_argument(
        "--force-baseline",
        action="store_true",
        help="Allow create mode to replace an existing reviewed baseline.",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=None,
        help="Combined JSON summary path. Default: <output-dir>/regression_batch_summary.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.hardware != "skip" and not args.resource:
        raise SystemExit("--resource is required for the hardware stage")

    tests = discover_regression_tests()
    if not tests and not args.all_tests:
        raise SystemExit("No regression tests discovered")

    print("DPO4000 regression batch", flush=True)
    if not args.all_tests:
        print("Software regression files:", flush=True)
        for path in _relative_strings(tests):
            print(f"  - {path}", flush=True)

    stages: list[StageResult] = []
    software = _run_stage("Software R0 regression", build_software_command(all_tests=args.all_tests))
    stages.append(software)

    hardware_requested = args.hardware != "skip"
    if hardware_requested and (
        software.return_code == 0 or args.continue_after_software_failure
    ):
        hardware_command = build_hardware_command(args)
        stages.append(_run_stage(f"Hardware R0 {args.hardware}", hardware_command))
    elif hardware_requested:
        print(
            "\nHardware stage SKIPPED because software regression failed. "
            "Use --continue-after-software-failure to override.",
            flush=True,
        )

    passed = all(stage.return_code == 0 for stage in stages)
    if hardware_requested and len(stages) == 1:
        passed = False

    output_dir = Path(args.output_dir).expanduser().resolve()
    summary_path = (
        args.summary.expanduser().resolve()
        if args.summary is not None
        else output_dir / "regression_batch_summary.json"
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if passed else "FAIL",
        "hardware_mode": args.hardware,
        "resource": args.resource or "",
        "stages": [asdict(stage) for stage in stages],
    }
    summary_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    print("\n=== Regression batch summary ===", flush=True)
    for stage in stages:
        print(f"{stage.name:28s} {stage.status:4s} {stage.duration_s:8.2f}s", flush=True)
    print(f"Overall: {'PASS' if passed else 'FAIL'}", flush=True)
    print(f"Summary: {summary_path}", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
