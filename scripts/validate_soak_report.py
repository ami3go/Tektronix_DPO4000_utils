#!/usr/bin/env python3
"""Fail-closed offline validation of retained DPO4054 soak evidence.

This checks report consistency and acceptance policy, not the authenticity of
physical hardware. Independent bench evidence review remains mandatory.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any


def _finite_nonnegative(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (float, int))
        and math.isfinite(value)
        and value >= 0
    )


def validate_soak_report(
    report_dir: Path, *, min_hours: float = 24.0, expected_commit: str | None = None
) -> tuple[list[str], dict[str, str]]:
    """Return failure reasons and SHA-256 hashes for the reviewed artifacts."""
    reasons: list[str] = []
    evidence: dict[str, str] = {}
    raw_files: dict[str, bytes] = {}
    if not math.isfinite(min_hours) or min_hours < 24:
        return ["Minimum approved qualification duration is 24 hours"], evidence
    paths = {
        "json": report_dir / "soak_report.json",
        "markdown": report_dir / "soak_report.md",
    }
    for name, path in paths.items():
        try:
            if path.is_symlink() or report_dir.is_symlink():
                raise ValueError(f"Symlink qualification evidence rejected: {path}")
            raw = path.read_bytes()
        except (OSError, ValueError) as exc:
            reasons.append(f"Missing or unsafe {name} evidence: {exc}")
            continue
        if not raw or len(raw) > 100_000_000:
            reasons.append(f"Empty or oversized {name} evidence")
            continue
        raw_files[name] = raw
        evidence[name] = hashlib.sha256(raw).hexdigest()
    if len(evidence) != 2:
        return reasons, evidence

    def unique_keys(pairs: list[tuple[str, Any]]) -> dict:
        item = {}
        for key, value in pairs:
            if key in item:
                raise ValueError(f"Duplicate JSON key: {key}")
            item[key] = value
        return item

    try:
        # Parse the exact bytes whose digest was retained. Reopening permits a
        # concurrent replacement to make the judged report differ from its hash.
        payload = json.loads(raw_files["json"].decode("utf-8"),
                             parse_constant=lambda value: (_ for _ in ()).throw(
                                 ValueError(f"Nonstandard number {value}")),
                             object_pairs_hook=unique_keys)
    except (ValueError, UnicodeError, OSError) as exc:
        return [*reasons, f"Invalid JSON evidence: {exc}"], evidence
    if not isinstance(payload, dict):
        return [*reasons, "Root evidence must be an object"], evidence
    summary = payload.get("summary")
    samples = payload.get("samples")
    failures = payload.get("failures")
    if not isinstance(summary, dict) or not isinstance(samples, list) or not isinstance(failures, list):
        return [*reasons, "Missing or invalid summary/samples/failures"], evidence
    if summary.get("schema_version") != 2:
        reasons.append("Unsupported or absent soak evidence schema")
    if summary.get("run_state") != "FINAL" or summary.get("status") != "PASS":
        reasons.append("Run not finalized in PASS state")
    for field in ("requested_duration_hours", "elapsed_s"):
        if not _finite_nonnegative(summary.get(field)):
            reasons.append(f"Missing or nonfinite {field}")
    required_s = max(24.0, min_hours) * 3600.0
    elapsed = summary.get("elapsed_s")
    if _finite_nonnegative(elapsed) and elapsed < required_s:
        reasons.append(f"Run shorter than minimum qualification: {elapsed:.3f}s < {required_s:.3f}s")
    duration = summary.get("requested_duration_hours")
    if _finite_nonnegative(duration) and duration < min_hours:
        reasons.append("Requested duration less than qualification minimum")
    identity = summary.get("baseline_identity")
    if not isinstance(identity, str) or "DPO4054" not in identity.upper():
        reasons.append("Missing verified physical DPO4054 identity")
    if not identity or summary.get("final_identity") != identity:
        reasons.append("Missing/mismatched final instrument identity")
    if expected_commit and summary.get("commit_sha") != expected_commit:
        reasons.append("Git commit does not match qualified checkout")
    if not summary.get("commit_sha"):
        reasons.append("Missing source commit")
    if summary.get("cleanup_errors") or summary.get("failure_reasons"):
        reasons.append("Report contains cleanup errors or failure reasons")
    if summary.get("successful_samples") != len(samples):
        reasons.append("Successful cycle count differs from raw samples")
    if summary.get("failures") != len(failures):
        reasons.append("Failure count differs from raw failures")
    if summary.get("cycles") != len(samples) + len(failures):
        reasons.append("Reported total cycle count differs from raw evidence")
    if not samples:
        reasons.append("No successful instrument cycles")
    if not isinstance(summary.get("cleanup_errors"), list):
        reasons.append("Missing cleanup diagnostics")
    if not isinstance(summary.get("failure_reasons"), list):
        reasons.append("Missing completion diagnostics")
    if not isinstance(summary.get("resource"), str) or not summary["resource"].strip():
        reasons.append("Missing VISA resource identity")

    cycles = []
    latencies = []
    elapsed_samples = []
    ordered_records = sorted(
        [*samples, *failures],
        key=lambda item: (item.get("cycle") if type(item.get("cycle")) is int else -1)
        if isinstance(item, dict) else -1,
    )
    for record in ordered_records:
        if not isinstance(record, dict) or type(record.get("cycle")) is not int:
            reasons.append("Malformed cycle entry")
            continue
        cycles.append(record["cycle"])
        if not _finite_nonnegative(record.get("elapsed_s")):
            reasons.append("Invalid sample elapsed_s")
        else:
            elapsed_samples.append(record["elapsed_s"])
    if sorted(cycles) != list(range(1, len(cycles) + 1)):
        reasons.append("Cycle indices missing, duplicated or out of range")
    if elapsed_samples and (
        elapsed_samples != sorted(elapsed_samples)
        or (_finite_nonnegative(elapsed) and elapsed_samples[-1] > elapsed)
    ):
        reasons.append("Nonmonotonic or out-of-bounds cycle timestamps")
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        if sample.get("identity") != identity:
            reasons.append("Per-cycle instrument identity differs from baseline")
        latency = sample.get("cycle_duration_s")
        if not _finite_nonnegative(latency):
            reasons.append("Nonfinite or negative cycle latency")
        else:
            latencies.append(latency)
    missed = summary.get("missed_deadlines")
    expected_cycles = summary.get("expected_cycles")
    interval = summary.get("interval_seconds")
    if type(missed) is not int or missed < 0:
        reasons.append("Missing or negative missed-deadline count")
    if not _finite_nonnegative(interval) or interval == 0:
        reasons.append("Invalid scheduled interval")
    elif _finite_nonnegative(duration):
        if type(expected_cycles) is not int or expected_cycles != math.ceil(
            duration * 3600.0 / interval
        ):
            reasons.append("Inconsistent expected cycle count")
    # A lone sample plus forged 86400s duration previously passed. The runner
    # schedules one cycle per interval; all periods must be accounted for.
    if type(expected_cycles) is int and type(missed) is int and missed >= 0:
        accounted_for = len(ordered_records) + missed
        if accounted_for < expected_cycles - 1:
            reasons.append("Scheduled sample coverage incomplete")
        if accounted_for > expected_cycles + 1:
            reasons.append("Cycle/deadline accounting exceeds planned schedule")
    if (_finite_nonnegative(interval) and interval > 0
        and elapsed_samples and _finite_nonnegative(elapsed)):
        # Allow one cycle period plus the maximum accepted operation latency.
        max_latency = summary.get("acceptance_limits", {})
        max_latency = (max_latency.get("max_cycle_latency_s") if isinstance(max_latency, dict)
                       else None)
        if not _finite_nonnegative(max_latency):
            reasons.append("Missing safe cycle-latency bound")
        else:
            grace = interval + max_latency
            if elapsed_samples[0] > grace:
                reasons.append("Soak has no initial scheduled-cycle evidence")
            if elapsed_samples[-1] < required_s - grace:
                reasons.append("Soak has no final scheduled-cycle evidence")
            for earlier, later in zip(elapsed_samples, elapsed_samples[1:]):
                if later - earlier > 2 * (interval + max_latency):
                    reasons.append("Unexplained gap in scheduled cycles")
                    break
    limits = summary.get("acceptance_limits")
    if not isinstance(limits, dict):
        reasons.append("Acceptance limits not retained")
    else:
        max_missed = limits.get("max_missed_deadlines")
        if not _finite_nonnegative(max_missed) or (
            type(missed) is int and missed > max_missed
        ):
            reasons.append("Missed periodic deadlines exceed retained limit")
        if not _finite_nonnegative(limits.get("max_failures")) or (
            len(failures) > limits.get("max_failures", -1)
        ):
            reasons.append("Failure count violates retained limit")
        if not _finite_nonnegative(limits.get("max_cycle_latency_s")):
            reasons.append("Invalid retained cycle-latency bound")
        elif latencies and max(latencies) > limits["max_cycle_latency_s"]:
            reasons.append("Cycle latency violates retained limit")
        for key in ("max_rss_growth_mib", "max_python_growth_mib",
                    "max_fd_growth", "max_thread_growth", "max_latency_drift_factor"):
            if not _finite_nonnegative(limits.get(key)):
                reasons.append(f"Missing or invalid acceptance limit: {key}")
        for metric, limit, scale in (
            ("rss_bytes", "max_rss_growth_mib", 1024 * 1024),
            ("python_current_bytes", "max_python_growth_mib", 1024 * 1024),
            ("fd_count", "max_fd_growth", 1),
            ("thread_count", "max_thread_growth", 1),
        ):
            values = [sample.get(metric) for sample in samples if isinstance(sample, dict)
                      and sample.get(metric) is not None]
            if any(not _finite_nonnegative(value) for value in values):
                reasons.append(f"Invalid resource metric: {metric}")
            elif values and _finite_nonnegative(limits.get(limit)):
                if max(values) - values[0] > limits[limit] * scale:
                    reasons.append(f"Resource growth exceeded bound: {metric}")
            if metric in ("python_current_bytes", "thread_count") and len(values) != len(samples):
                reasons.append(f"Missing mandatory resource metric: {metric}")
        if len(latencies) >= 100 and _finite_nonnegative(
            limits.get("max_latency_drift_factor")
        ):
            import statistics
            quarter = max(10, len(latencies) // 4)
            chronological = [record.get("cycle_duration_s") for record in samples
                             if isinstance(record, dict)]
            if all(_finite_nonnegative(value) for value in chronological):
                early = statistics.median(chronological[:quarter])
                late = statistics.median(chronological[-quarter:])
                if late > early * limits["max_latency_drift_factor"] and late - early > 0.5:
                    reasons.append("Progressive cycle-latency drift exceeds bound")
    try:
        began = datetime.fromisoformat(summary["started_at"])
        finished = datetime.fromisoformat(summary["finished_at"])
        if began.tzinfo is None or finished.tzinfo is None or finished <= began:
            reasons.append("Invalid UTC start/end timestamps")
        elif _finite_nonnegative(elapsed):
            wall_seconds = (finished - began).total_seconds()
            # Allow bounded host clock/NTP corrections. These timestamps are
            # consistency evidence, not a substitute for monotonic coverage.
            if abs(wall_seconds - elapsed) > max(120.0, required_s * 0.005):
                reasons.append("Wall duration contradicts reported monotonic duration")
            if wall_seconds < required_s - 120.0:
                reasons.append("Real-time evidence shorter than requested soak")
    except (KeyError, TypeError, ValueError):
        reasons.append("Missing or malformed start/end timestamps")
    markdown = raw_files["markdown"].decode("utf-8")
    if "**Status:** PASS" not in markdown or "# DPO4000 hardware soak qualification" not in markdown:
        reasons.append("Human-readable report missing finalized PASS status")
    return reasons, evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--min-hours", type=float, choices=(24.0, 72.0), default=24.0)
    parser.add_argument("--expected-commit")
    args = parser.parse_args()
    issues, hashes = validate_soak_report(
        args.report_dir, min_hours=args.min_hours, expected_commit=args.expected_commit
    )
    for name, digest in hashes.items():
        print(f"{name} SHA256: {digest}")
    for issue in issues:
        print(f"FAIL: {issue}")
    print("Soak evidence: " + ("FAIL" if issues else "STRUCTURALLY_VALID — requires bench review"))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
