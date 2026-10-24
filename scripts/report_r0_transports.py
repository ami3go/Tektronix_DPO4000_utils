#!/usr/bin/env python3
"""Offline USB/TCPIP R0 qualification rollup; never opens VISA or approves thresholds.

A missing measurement, unapproved threshold, corrupt raw capture, mismatch, or
unqualified feature is BLOCKED/FAIL, never an inferred hardware PASS.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

REQUIRED_EXTENSIONS = (
    "transport_throughput",
    "a15_recipe_execution",
    "a18_evidence_generation",
    "a21_npz_export",
    "a21_dpoz_export",
    "a25_headless_overhead",
    "cancellation_and_error_recovery",
    "resource_usage",
    "gui_responsiveness",
)
CORE_OPERATIONS = (
    "connection",
    "identity_query",
    "channel_readback",
    "measurement_refresh",
    "trigger_config_apply",
    "trigger_config_readback",
    "single_acquisition",
    "png_capture",
    "csv_export",
    "waveform_acquisition.1000",
    "waveform_acquisition.10000",
    "waveform_acquisition.100000",
    "waveform_acquisition.1000000",
)
FIELDS = (
    "transport", "operation", "baseline_n", "candidate_n",
    "baseline_p50_s", "candidate_p50_s", "baseline_p95_s",
    "candidate_p95_s", "candidate_p99_s", "candidate_max_s",
    "candidate_stdev_s", "absolute_delta_p95_s", "relative_delta_p95_percent",
    "candidate_samples_per_second", "transport_mb_per_second",
    "threshold_relative_limit", "threshold_absolute_tolerance_s", "regressed",
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(mode="wb", dir=path.parent, prefix=f".{path.name}.",
                                suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _read(root: Path, relative: str, hashes: dict[str, str],
          issues: list[str]) -> dict[str, Any]:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        issues.append(f"Missing/unsafe evidence: {relative}")
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("JSON root must be an object")
    except (OSError, UnicodeError, ValueError) as error:
        issues.append(f"Invalid evidence {relative}: {error}")
        return {}
    hashes[relative] = _digest(path)
    return document


def _flatten(operations: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(operations, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for name, value in operations.items():
        if name == "waveform_acquisition" and isinstance(value, dict):
            result.update({
                f"waveform_acquisition.{size}": entry
                for size, entry in value.items() if isinstance(entry, dict)
            })
        elif isinstance(value, dict) and "p95" in value:
            result[name] = value
    return result


def _raw_ok(stats: dict[str, Any]) -> bool:
    samples = stats.get("samples_s")
    if not isinstance(samples, list) or not samples:
        return False
    if type(stats.get("sample_count")) is not int or stats["sample_count"] != len(samples):
        return False
    if not all(type(x) in (int, float) and math.isfinite(x) and x >= 0 for x in samples):
        return False
    for name in ("p50", "p95", "max"):
        value = stats.get(name)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            return False
    ordered = sorted(samples)
    expected = {
        "p50": statistics.median(ordered),
        "p95": ordered[min(len(ordered) - 1, max(0, round(0.95 * (len(ordered) - 1))))],
        "max": ordered[-1],
    }
    if any(not math.isclose(stats[key], value, rel_tol=1e-10, abs_tol=1e-12)
           for key, value in expected.items()):
        return False
    p99 = stats.get("p99")
    if len(samples) < 100:
        if p99 is not None:
            return False
    elif type(p99) not in (int, float) or not math.isfinite(p99):
        return False
    return True


def _evidence_restored(document: dict[str, Any]) -> bool:
    data = document.get("setup_restoration")
    return isinstance(data, dict) and data.get("status") == "VERIFIED" and data.get("verified") is True


def _extension_issues(document: dict[str, Any], transport: str, idn: str,
                      candidate_sha: str) -> list[str]:
    reasons: list[str] = []
    if document.get("schema_version") != 1 or document.get("idn") != idn:
        reasons.append(f"{transport}: missing/inconsistent additional benchmark identity")
    if document.get("commit_sha") != candidate_sha or document.get("transport") != transport:
        reasons.append(f"{transport}: additional benchmarks have wrong transport/commit")
    metrics = document.get("metrics")
    if not isinstance(metrics, dict):
        return [*reasons, f"{transport}: extra measurement metrics absent"]
    for metric in REQUIRED_EXTENSIONS:
        observation = metrics.get(metric)
        if not isinstance(observation, dict):
            reasons.append(f"{transport}: unmeasured {metric}")
            continue
        if not _raw_ok(observation):
            reasons.append(f"{transport}: missing/corrupt raw observations for {metric}")
        if metric == "transport_throughput":
            if type(observation.get("payload_bytes")) is not int or observation["payload_bytes"] <= 0:
                reasons.append(f"{transport}: transport wire payload bytes not measured")
        if metric == "a21_npz_export" or metric == "a21_dpoz_export":
            if type(observation.get("file_bytes")) is not int or observation["file_bytes"] <= 0:
                reasons.append(f"{transport}: {metric} output bytes not measured")
    return reasons


def evaluate(root: Path, threshold_file: Path, approval_path: Path | None
             ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[str] = []
    hashes: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    idns: dict[str, str] = {}
    commits: dict[str, str] = {}
    baseline_commits: dict[str, str] = {}
    threshold_hash = _digest(threshold_file) if threshold_file.is_file() else None
    if threshold_hash is None:
        issues.append("Acceptance-threshold file absent")
        threshold_operations: dict[str, Any] = {}
    else:
        try:
            threshold_document = json.loads(threshold_file.read_text(encoding="utf-8"))
            threshold_operations = threshold_document["operations"]
            if not isinstance(threshold_operations, dict):
                raise ValueError("operations must be an object")
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
            issues.append(f"Malformed acceptance-threshold file: {error}")
            threshold_operations = {}
    approval_file = (
        (root / approval_path).resolve() if approval_path is not None
        and not approval_path.is_absolute()
        else approval_path.resolve() if approval_path is not None else None
    )
    approval = _read(root, str(approval_file.relative_to(root)), hashes, issues) if (
        approval_file is not None and approval_file.is_relative_to(root.resolve())
    ) else None
    if approval is None:
        issues.append("Independent threshold approval record absent or outside evidence root")
    elif (approval.get("status") != "APPROVED"
          or not approval.get("reviewer")
          or approval.get("threshold_sha256") != threshold_hash):
        issues.append("Independent threshold approval invalid or digest does not match")
    comparison_failed = False
    for transport in ("usb", "tcpip"):
        prefix = f"{transport}"
        base = _read(root, f"{prefix}/baseline/r0_timing_baseline.json", hashes, issues)
        base_f = _read(root, f"{prefix}/baseline/r0_functional_baseline.json", hashes, issues)
        candidate = _read(root, f"{prefix}/candidate/r0_candidate_timing.json", hashes, issues)
        cand_f = _read(root, f"{prefix}/candidate/r0_candidate_functional.json", hashes, issues)
        comparison = _read(root, f"{prefix}/candidate/comparison_report.json", hashes, issues)
        extensions = _read(root, f"{prefix}/candidate/r0_extra_metrics.json", hashes, issues)
        baseline_extensions = _read(
            root, f"{prefix}/baseline/r0_extra_metrics.json", hashes, issues
        )
        if any(not doc for doc in (base, base_f, candidate, cand_f, comparison)):
            issues.append(f"{transport}: incomplete R0 functional/timing evidence")
            continue
        if comparison.get("status") != "PASS":
            issues.append(f"{transport}: R0 comparison not PASS")
            comparison_failed = comparison.get("status") == "FAIL" or comparison_failed
        for issue_field in (
            "identity_issues", "restoration_issues", "configuration_issues",
            "timing_quality_issues", "unmeasured_thresholds", "unthresholded_operations",
            "known_coverage_gaps", "missing_operations", "functional_diffs",
        ):
            if comparison.get(issue_field):
                issues.append(f"{transport}: unresolved {issue_field}")
        if comparison.get("thresholds_sha256") != threshold_hash:
            issues.append(f"{transport}: threshold file has changed since comparison")
        for doc_name, doc in (("baseline timing", base), ("baseline functional", base_f),
                              ("candidate timing", candidate), ("candidate functional", cand_f)):
            if not _evidence_restored(doc):
                issues.append(f"{transport}: {doc_name} lacks verified restoration")
        idn = str(base.get("idn", ""))
        idns[transport] = idn
        commits[transport] = str(candidate.get("commit_sha", ""))
        baseline_commits[transport] = str(base.get("commit_sha", ""))
        if not idn or not all(doc.get("idn") == idn for doc in (base_f, candidate, cand_f)):
            issues.append(f"{transport}: instrument identity mismatch")
        if not all(doc.get("test_configuration") == base.get("test_configuration")
                   and isinstance(doc.get("test_configuration"), dict)
                   for doc in (base_f, candidate, cand_f)):
            issues.append(f"{transport}: capture configurations differ")
        for typ in ("functional", "timing"):
            key = f"{prefix}/candidate/r0_candidate_{typ}.json"
            if comparison.get(f"candidate_{typ}_sha256") != hashes.get(key):
                issues.append(f"{transport}: raw candidate {typ} hash mismatch")
        baselines = _flatten(base.get("operations"))
        candidates = _flatten(candidate.get("operations"))
        for name in CORE_OPERATIONS:
            if name not in baselines or name not in candidates:
                issues.append(f"{transport}: required timed operation {name} absent")
        if set(baselines) != set(candidates):
            issues.append(f"{transport}: candidate/baseline timing operation set differs")
        accepted = comparison.get("timing_regressions", [])
        accepted_by_op = {
            x["operation"]: x for x in accepted
            if isinstance(x, dict) and isinstance(x.get("operation"), str)
        } if isinstance(accepted, list) else {}
        for operation in sorted(set(baselines) | set(candidates)):
            b, c = baselines.get(operation, {}), candidates.get(operation, {})
            if not _raw_ok(b) or not _raw_ok(c):
                issues.append(f"{transport}: raw samples missing/corrupt for {operation}")
                continue
            recorded = accepted_by_op.get(operation)
            if not recorded:
                issues.append(f"{transport}: no acceptance gate for {operation}")
                continue
            diff = c["p95"] - b["p95"]
            relative = recorded.get("relative_limit")
            absolute = recorded.get("absolute_tolerance_s")
            if (type(relative) not in (int, float) or not math.isfinite(relative)
                or relative < 1 or type(absolute) not in (int, float)
                or not math.isfinite(absolute) or absolute < 0):
                issues.append(f"{transport}: invalid acceptance limits for {operation}")
                continue
            computed_regressed = c["p95"] > b["p95"] * relative and diff > absolute
            if computed_regressed:
                comparison_failed = True
                issues.append(f"{transport}: regression in {operation}")
            if (recorded.get("regressed") is not computed_regressed
                or recorded.get("baseline_value") != b["p95"]
                or recorded.get("candidate_value") != c["p95"]):
                comparison_failed = True
                issues.append(f"{transport}: comparison metric/verdict mismatched for {operation}")
            rows.append({
                "transport": transport, "operation": operation,
                "baseline_n": b["sample_count"], "candidate_n": c["sample_count"],
                "baseline_p50_s": b["p50"], "candidate_p50_s": c["p50"],
                "baseline_p95_s": b["p95"], "candidate_p95_s": c["p95"],
                "candidate_p99_s": c.get("p99"), "candidate_max_s": c["max"],
                "candidate_stdev_s": c.get("stdev"),
                "absolute_delta_p95_s": diff,
                "relative_delta_p95_percent": (100 * diff / b["p95"]) if b["p95"] > 0 else None,
                "candidate_samples_per_second": c.get("samples_per_second"),
                "transport_mb_per_second": c.get("transport_mb_per_second"),
                "threshold_relative_limit": recorded.get("relative_limit"),
                "threshold_absolute_tolerance_s": recorded.get("absolute_tolerance_s"),
                "regressed": computed_regressed,
            })
        issues.extend(_extension_issues(extensions, transport, idn, commits[transport]))
        issues.extend(_extension_issues(
            baseline_extensions, transport, idn, baseline_commits[transport]
        ))
        old_metrics = baseline_extensions.get("metrics", {})
        new_metrics = extensions.get("metrics", {})
        if not isinstance(old_metrics, dict) or not isinstance(new_metrics, dict):
            continue
        for operation in REQUIRED_EXTENSIONS:
            previous = old_metrics.get(operation)
            current = new_metrics.get(operation)
            if not isinstance(previous, dict) or not isinstance(current, dict):
                continue
            if not _raw_ok(previous) or not _raw_ok(current):
                continue
            limits = threshold_operations.get(operation)
            if not isinstance(limits, dict):
                issues.append(f"{transport}: no approved threshold entry for {operation}")
                continue
            relative, absolute = limits.get("relative_limit"), limits.get("absolute_tolerance_s")
            if (type(relative) not in (int, float) or not math.isfinite(relative)
                or relative < 1 or type(absolute) not in (int, float)
                or not math.isfinite(absolute) or absolute < 0):
                issues.append(f"{transport}: invalid threshold entry for {operation}")
                continue
            delta = current["p95"] - previous["p95"]
            regressed = current["p95"] > previous["p95"] * relative and delta > absolute
            if regressed:
                comparison_failed = True
                issues.append(f"{transport}: feature regression {operation}")
            byte_field = (
                "payload_bytes" if operation == "transport_throughput"
                else "file_bytes" if operation.startswith("a21_") else None
            )
            bytes_measured = current.get(byte_field) if byte_field else None
            throughput = (
                bytes_measured / current["p50"] / 1_000_000
                if type(bytes_measured) is int and bytes_measured > 0
                and current["p50"] > 0 else None
            )
            rows.append({
                "transport": transport, "operation": operation,
                "baseline_n": previous["sample_count"], "candidate_n": current["sample_count"],
                "baseline_p50_s": previous["p50"], "candidate_p50_s": current["p50"],
                "baseline_p95_s": previous["p95"], "candidate_p95_s": current["p95"],
                "candidate_p99_s": current.get("p99"), "candidate_max_s": current["max"],
                "candidate_stdev_s": current.get("stdev"),
                "absolute_delta_p95_s": delta,
                "relative_delta_p95_percent": (
                    100 * delta / previous["p95"] if previous["p95"] > 0 else None
                ),
                "candidate_samples_per_second": current.get("samples_per_second"),
                "transport_mb_per_second": throughput,
                "threshold_relative_limit": relative,
                "threshold_absolute_tolerance_s": absolute, "regressed": regressed,
            })
    baseline_digests = approval.get("baseline_sha256", {}) if isinstance(approval, dict) else {}
    for transport in ("usb", "tcpip"):
        for kind in ("functional", "timing"):
            relative = f"{transport}/baseline/r0_{kind}_baseline.json"
            if not isinstance(baseline_digests, dict) or (
                baseline_digests.get(relative) != hashes.get(relative)
            ):
                issues.append(f"No approved immutable baseline hash for {relative}")
        relative = f"{transport}/baseline/r0_extra_metrics.json"
        if not isinstance(baseline_digests, dict) or (
            baseline_digests.get(relative) != hashes.get(relative)
        ):
            issues.append(f"No approved immutable baseline hash for {relative}")
    if approval and approval.get("known_good_commit_sha") not in set(baseline_commits.values()):
        issues.append("Approved known-good baseline commit does not match captured baselines")
    if len(set(idns.values())) != 1 or len(idns) != 2:
        issues.append("USB and TCPIP do not identify the same physical scope")
    if len(set(commits.values())) != 1 or len(commits) != 2:
        issues.append("USB and TCPIP were not captured from the same candidate commit")
    if len(set(baseline_commits.values())) != 1 or len(baseline_commits) != 2:
        issues.append("USB and TCPIP baseline commits differ")
    return ({
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "FAIL" if comparison_failed else "BLOCKED" if issues else "PASS",
        "issues": sorted(set(issues)), "identities": idns, "candidate_commits": commits,
        "baseline_commits": baseline_commits, "threshold_sha256": threshold_hash,
        "threshold_approval": approval if approval else None,
        "artifacts_sha256": hashes, "operations_compared": len(rows),
        "note": "Offline structural evaluation only: human bench and reviewer attestation required.",
    }, rows)


def _write_optional_plots(rows: list[dict[str, Any]], output: Path) -> None:
    """Plot matched p95 values when measured rows and matplotlib are available."""
    if not rows:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import pyplot as plt
    except ImportError:
        print("Optional matplotlib unavailable; CSV/JSON contain the complete measured data")
        return
    for transport in ("usb", "tcpip"):
        selected = [item for item in rows if item["transport"] == transport]
        if not selected:
            continue
        positions = list(range(len(selected)))
        fig, ax = plt.subplots(figsize=(max(9, len(selected) * 0.45), 6))
        ax.bar([v - 0.2 for v in positions],
               [item["baseline_p95_s"] for item in selected], width=0.4,
               label="Approved baseline p95")
        ax.bar([v + 0.2 for v in positions],
               [item["candidate_p95_s"] for item in selected], width=0.4,
               label="Candidate p95")
        ax.set_xticks(positions, [item["operation"] for item in selected],
                      rotation=80, ha="right")
        ax.set_ylabel("Elapsed time (s, monotonic)")
        ax.set_title(f"{transport.upper()} R0 p95 operation latencies")
        ax.legend()
        fig.tight_layout()
        fig.savefig(output / f"{transport}_p95.png", dpi=140)
        plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("qualification_reports/performance"))
    parser.add_argument("--thresholds", type=Path, default=Path("tests/baselines/r0_timing_thresholds.json"))
    parser.add_argument("--approval", type=Path, default=None,
                        help="Existing signed-off review JSON under the performance root (never generated).")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    output = (args.output_dir or root / "transport_comparison").resolve()
    if output in (root / "usb" / "baseline", root / "tcpip" / "baseline"):
        parser.error("Refusing to write into an approved baseline folder")
    report, rows = evaluate(root, args.thresholds, args.approval)
    _atomic(output / "transport_comparison.json",
            (json.dumps({**report, "operations": rows}, sort_keys=True, indent=2,
                        allow_nan=False) + "\n").encode("utf-8"))
    from io import StringIO
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    _atomic(output / "transport_comparison.csv", buffer.getvalue().encode("utf-8"))
    lines = ["# USB / Ethernet R0 transport comparison", "",
             f"Status: **{report['status']}**", "",
             f"Operations with complete timing evidence: {len(rows)}", "",
             "## Outstanding acceptance blockers", ""]
    lines.extend(f"- {issue}" for issue in report["issues"])
    lines.extend(["", "No unsupported measurement or human approval is inferred.", ""])
    _atomic(output / "transport_comparison.md", "\n".join(lines).encode("utf-8"))
    _write_optional_plots(rows, output)
    print(f"R0 transport qualification: {report['status']} ({len(report['issues'])} blockers)")
    print(f"Evidence report: {output / 'transport_comparison.json'}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
