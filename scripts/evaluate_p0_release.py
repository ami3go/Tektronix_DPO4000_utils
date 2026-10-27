#!/usr/bin/env python3
"""Offline, fail-closed P0 v0.9 qualification manifest evaluator.

No VISA/SCPI access. Inputs must be genuine retained CI and instrument evidence,
independently reviewed. A structurally valid manifest is not proof of hardware
authenticity or authorization.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import math
import re
import statistics
from pathlib import Path
from tempfile import NamedTemporaryFile
import xml.etree.ElementTree as ET

from validate_soak_report import validate_soak_report
from dpo4000_utils.baseline_compare import diff_functional, diff_timing, load_thresholds

REQUIRED_CI = (
    "python_3_10", "python_3_11", "python_3_12", "python_3_13",
    "ruff", "pyside6", "codeql", "package_windows", "package_linux",
    "r0_offline_batch", "release_integrity",
)
REQUIRED_HIL = (
    "core", "channels_math_ref_bus", "waveform", "acquisition",
    "A14", "A15", "A16", "A18", "A20", "A21", "A25",
) + tuple(f"A{i}" for i in range(1, 13)) + tuple(f"L{i}" for i in range(1, 15))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.",
            suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    """Duplicate JSON keys must not silently replace failing evidence."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _evidence_path(root: Path, relative: str) -> Path:
    """Reject traversal, absolute paths and symlinks at every evidence component."""
    requested = Path(relative)
    if requested.is_absolute() or ".." in requested.parts or not requested.parts:
        raise ValueError(f"Unsafe evidence path: {relative}")
    path = root
    for component in requested.parts:
        path = path / component
        if path.is_symlink():
            raise ValueError(f"Symlink evidence not allowed: {relative}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Evidence outside qualification root: {relative}")
    return path


def _track_file(root: Path, relative: str, tracked: dict[str, str]) -> Path:
    path = _evidence_path(root, relative)
    if not path.is_file():
        raise FileNotFoundError(path)
    size = path.stat().st_size
    if not 0 < size <= 100_000_000:
        raise ValueError(f"Empty or oversized evidence: {relative}")
    tracked[relative] = _sha(path)
    return path


def _load(path: Path, tracked: dict[str, str], root: Path) -> dict:
    # POSIX form: callers look evidence up with "/" paths, also on Windows.
    relative = path.relative_to(root).as_posix()
    # Hash and parse the same bytes: separate hash/read operations permit
    # a concurrent file replacement to change the judged evidence.
    path = _evidence_path(root, relative)
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("rb") as handle:
        raw = handle.read(100_000_001)
    if not 0 < len(raw) <= 100_000_000:
        raise ValueError(f"Empty or oversized evidence: {relative}")
    payload = json.loads(
        raw.decode("utf-8"),
        parse_constant=_reject_constant,
        object_pairs_hook=_unique_object,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"Evidence must be an object: {relative}")
    tracked[relative] = hashlib.sha256(raw).hexdigest()
    return payload


def _operation_names(operations: dict) -> set[str]:
    result = set()
    for name, stats in operations.items():
        if name == "not_yet_covered":
            continue
        if name == "waveform_acquisition" and isinstance(stats, dict):
            result.update(f"waveform_acquisition.{size}" for size, item in stats.items()
                          if isinstance(item, dict) and "p95" in item)
        elif isinstance(stats, dict) and "p95" in stats:
            result.add(name)
    return result


def _validate_numeric_tree(item: object) -> None:
    if isinstance(item, dict):
        for child in item.values():
            _validate_numeric_tree(child)
    elif isinstance(item, list):
        for child in item:
            _validate_numeric_tree(child)
    elif isinstance(item, float) and not math.isfinite(item):
        raise ValueError("Evidence includes a nonfinite number")



def _raw_timing_issues(operations: dict, label: str) -> list[str]:
    """Cross-check reported percentiles against complete raw monotonic observations."""
    issues = []
    flattened = {}
    for name, stats in operations.items():
        if name == "not_yet_covered":
            continue
        if name == "waveform_acquisition" and isinstance(stats, dict):
            flattened.update({f"{name}.{size}": item for size, item in stats.items()})
        else:
            flattened[name] = stats
    for name, stats in flattened.items():
        if not isinstance(stats, dict):
            issues.append(f"{label}: invalid timing operation {name}")
            continue
        samples = stats.get("samples_s")
        if (not isinstance(samples, list) or not samples
            or type(stats.get("sample_count")) is not int
            or stats["sample_count"] != len(samples)
            or any(type(value) not in (float, int) or not math.isfinite(value)
                   or value < 0 for value in samples)):
            issues.append(f"{label}: invalid or absent raw duration observations: {name}")
            continue
        if (type(stats.get("error_count")) is not int or stats["error_count"] != 0
            or type(stats.get("timeout_count")) is not int or stats["timeout_count"] != 0):
            issues.append(f"{label}: timing observation failures/timeouts: {name}")
        ordered = sorted(samples)
        # Matches the committed baseline_capture.distribution nearest-rank policy.
        expected = {
            "min": ordered[0],
            "max": ordered[-1],
            "p50": statistics.median(ordered),
            "p95": ordered[round(0.95 * (len(ordered) - 1))],
        }
        for metric, number in expected.items():
            claimed = stats.get(metric)
            if (type(claimed) not in (float, int)
                or not math.isfinite(claimed)
                or not math.isclose(claimed, number, rel_tol=1e-12, abs_tol=1e-12)):
                issues.append(f"{label}: reported {metric} contradicts raw samples: {name}")
    for size in (1000, 10000, 100000, 1000000):
        if f"waveform_acquisition.{size}" not in flattened:
            issues.append(f"{label}: missing required waveform timing size {size}")
    if not flattened:
        issues.append(f"{label}: timing coverage is empty")
    return issues


def _reject_constant(token: str):
    raise ValueError(f"Nonstandard JSON number: {token}")


def _findings(*, failed: list[str], blocked: list[str]) -> dict:
    """Completed failures always outrank pending/missing qualification evidence."""
    return {
        "state": "FAIL" if failed else "BLOCKED" if blocked else "PASS",
        "reasons": [*failed, *blocked],
    }


def _gate(fn) -> dict:
    try:
        findings = fn()
    except FileNotFoundError as exc:
        return {"state": "BLOCKED", "reasons": [f"Missing evidence: {exc.filename or exc}"]}
    except Exception as exc:
        # Malformed, contradictory or unsafe evidence must never become BLOCKED.
        # KeyboardInterrupt and SystemExit still propagate.
        return {"state": "FAIL", "reasons": [f"Invalid evidence: {exc}"]}
    if isinstance(findings, dict):
        if (findings.get("state") not in {"PASS", "BLOCKED", "FAIL"}
            or not isinstance(findings.get("reasons"), list)):
            return {"state": "FAIL", "reasons": ["Invalid gate findings contract"]}
        return findings
    return {"state": "PASS" if not findings else "FAIL", "reasons": findings}


def evaluate(root: Path, *, commit: str) -> dict:
    """Evaluate all gates without opening an instrument session."""
    if len(commit) != 40 or any(ch not in "0123456789abcdef" for ch in commit.lower()):
        raise ValueError("--expected-commit must be an exact 40-digit Git SHA")
    if root.is_symlink():
        raise ValueError("Qualification evidence root must not be a symlink")
    root = root.resolve()
    tracked: dict[str, str] = {}
    parsed: dict[str, dict] = {}

    def load(relative: str) -> dict:
        # A document is read/hashed once per evaluation; never re-read the same
        # attacker-controlled path after it has already been judged.
        if relative not in parsed:
            parsed[relative] = _load(root / relative, tracked, root)
        return parsed[relative]

    def software() -> list[str]:
        data = load("software/ci.json")
        reasons = []
        if data.get("schema_version") != 1 or data.get("commit_sha") != commit:
            reasons.append("Software CI schema or commit mismatch")
        blocked = []
        jobs = data.get("jobs")
        if jobs is None:
            blocked.append("Required CI jobs matrix has not been supplied")
            return _findings(failed=reasons, blocked=blocked)
        if not isinstance(jobs, dict):
            return _findings(failed=[*reasons, "Invalid CI jobs matrix"], blocked=blocked)
        for name in REQUIRED_CI:
            job = jobs.get(name)
            if job is None:
                blocked.append(f"Missing required CI job: {name}")
                continue
            if not isinstance(job, dict):
                reasons.append(f"Invalid CI job record: {name}")
                continue
            status = job.get("status")
            if status in ("NOT_RUN", "UNKNOWN", "PENDING", "SKIPPED", "CANCELLED"):
                blocked.append(f"Required CI job not successfully executed: {name}: {status}")
                continue
            if (status != "PASS" or job.get("commit_sha") != commit
                or not isinstance(job.get("url"), str)
                or not re.fullmatch(
                    r"https://github\.com/ami3go/Tektronix_DPO4000_utils/actions/runs/[0-9]+(?:/job/[0-9]+)?",
                    job["url"],
                )):
                reasons.append(f"No exact-head traceable CI run: {name}")
        return _findings(failed=reasons, blocked=blocked)

    def hardware() -> list[str]:
        data = load("hardware/qualification.json")
        reasons = []
        if data.get("schema_version") != 1 or data.get("commit_sha") != commit:
            reasons.append("Hardware evidence schema or commit mismatch")
        if "DPO4054" not in str(data.get("idn", "")).upper():
            reasons.append("Missing real DPO4054 identity")
        if data.get("setup_restored") is not True:
            reasons.append("Initial instrument setup was not independently verified restored")
        cases = data.get("cases")
        if cases is None:
            return _findings(failed=reasons, blocked=["HIL feature cases not supplied"])
        if not isinstance(cases, list):
            return _findings(failed=[*reasons, "Invalid HIL feature cases"], blocked=[])
        blocked = []
        by_name = {
            item["id"]: item for item in cases
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        ids = [item.get("id") for item in cases if isinstance(item, dict)]
        if len(ids) != len(cases) or len(ids) != len(set(ids)):
            reasons.append("Invalid or duplicate HIL case IDs")
        for name in REQUIRED_HIL:
            case = by_name.get(name)
            if not case:
                blocked.append(f"Missing physical feature qualification: {name}")
                continue
            status = case.get("status")
            if status != "PASS":
                # All required feature IDs are mandatory. An unsupported capability
                # needs a separate approved exception, never an automatic PASS.
                reasons.append(f"HIL case {name} not PASS: {status}")
            artifact = case.get("artifact")
            if not isinstance(artifact, str) or not artifact.strip():
                blocked.append(f"Missing retained case evidence path: {name}")
                continue
            # Track case evidence hashes; JSON documents are already checked
            # by their respective test runners and must be reviewed on the bench.
            try:
                _track_file(root, artifact, tracked)
                actual_digest = tracked[artifact]
                if (not isinstance(case.get("artifact_sha256"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", case["artifact_sha256"])
                    or case["artifact_sha256"] != actual_digest):
                    reasons.append(f"HIL evidence SHA256 missing/mismatch for {name}")
            except FileNotFoundError as exc:
                blocked.append(f"Missing HIL artifact for {name}: {exc}")
            except (OSError, ValueError) as exc:
                reasons.append(f"Missing/unsafe HIL artifact for {name}: {exc}")
        return _findings(failed=reasons, blocked=blocked)

    def performance() -> list[str] | dict:
        """Recompute regression decisions from raw evidence, never trust status alone."""
        reasons = []
        # Inspect *all* required inputs before deep comparison. Otherwise an
        # absent USB artifact could conceal a confirmed TCPIP failure, or vice
        # versa, depending on file evaluation order.
        paths = ["performance/transport_comparison/transport_comparison.json"]
        for transport in ("usb", "tcpip"):
            base = f"performance/{transport}"
            paths.extend([
                f"{base}/candidate/comparison_report.json",
                f"{base}/baseline/r0_functional_baseline.json",
                f"{base}/baseline/r0_timing_baseline.json",
                f"{base}/candidate/r0_candidate_functional.json",
                f"{base}/candidate/r0_candidate_timing.json",
                f"{base}/candidate/r0_extra_metrics.json",
                f"{base}/baseline/r0_extra_metrics.json",
            ])
        missing: list[str] = []
        failed: list[str] = []
        for relative in paths:
            try:
                data = load(relative)
            except FileNotFoundError:
                missing.append(f"Missing R0 evidence: {relative}")
                continue
            except Exception as exc:
                failed.append(f"Invalid R0 evidence {relative}: {exc}")
                continue
            if relative.endswith("/comparison_report.json"):
                if data.get("status") not in ("PASS", "PENDING", "NOT_RUN"):
                    failed.append(f"R0 comparison explicitly failed or invalid: {relative}")
                elif data.get("status") != "PASS":
                    missing.append(f"R0 comparison not executed: {relative}")
            elif relative.endswith("/transport_comparison.json"):
                if data.get("status") not in ("PASS", "PENDING", "NOT_RUN"):
                    failed.append("USB/TCPIP comparison explicitly failed or invalid")
                elif data.get("status") != "PASS":
                    missing.append("USB/TCPIP rollup not yet approved")
            elif "/candidate/r0_candidate_" in relative:
                if data.get("commit_sha") != commit:
                    failed.append(f"R0 candidate commit mismatch: {relative}")
        if missing or failed:
            return _findings(failed=failed, blocked=missing)
        # This reviewed threshold file belongs to the executing, versioned checkout.
        # A threshold change requires a code-reviewed commit, not candidate input.
        policy_path = Path(__file__).resolve().parents[1] / "tests/baselines/r0_timing_thresholds.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"),
                            parse_constant=_reject_constant, object_pairs_hook=_unique_object)
        thresholds = load_thresholds(policy)
        for name, threshold in thresholds.items():
            if (not math.isfinite(threshold.relative_limit) or threshold.relative_limit <= 0
                or not math.isfinite(threshold.absolute_tolerance_s)
                or threshold.absolute_tolerance_s < 0):
                raise ValueError(f"Invalid reviewed timing threshold: {name}")

        for transport in ("usb", "tcpip"):
            base = f"performance/{transport}"
            data = load(f"{base}/candidate/comparison_report.json")
            baseline_f = load(f"{base}/baseline/r0_functional_baseline.json")
            baseline_t = load(f"{base}/baseline/r0_timing_baseline.json")
            candidate_f = load(f"{base}/candidate/r0_candidate_functional.json")
            candidate_t = load(f"{base}/candidate/r0_candidate_timing.json")
            documents = (baseline_f, baseline_t, candidate_f, candidate_t)
            idns = {doc.get("idn") for doc in documents}
            families = {str(doc.get("resource", "")).split("::")[0].upper()
                        for doc in documents}
            if (len(idns) != 1 or not all(isinstance(doc.get("idn"), str)
                    and "DPO4054" in doc["idn"].upper() for doc in documents)):
                reasons.append(f"{transport}: baseline/candidate scope identities mismatch")
            if len(families) != 1 or not next(iter(families)).startswith(
                "USB" if transport == "usb" else "TCPIP"
            ):
                reasons.append(f"{transport}: missing/mismatched transport")
            if any(doc.get("schema_version") != 1 for doc in documents):
                reasons.append(f"{transport}: unsupported raw evidence schema")
            if (any(not isinstance(doc.get("commit_sha"), str)
                    or not re.fullmatch(r"[0-9a-fA-F]{40}", doc["commit_sha"])
                    for doc in (baseline_f, baseline_t))
                or baseline_f.get("commit_sha") != baseline_t.get("commit_sha")):
                reasons.append(f"{transport}: inconsistent approved baseline commit")
            if any(doc.get("commit_sha") != commit for doc in (candidate_f, candidate_t)):
                reasons.append(f"{transport}: candidate must come from exact qualified commit")
            configurations = [doc.get("test_configuration") for doc in documents]
            if not all(isinstance(config, dict) and config
                       and config == configurations[0] for config in configurations):
                reasons.append(f"{transport}: missing or inconsistent capture configuration")
            for doc in documents:
                restoration = doc.get("setup_restoration")
                if (not isinstance(restoration, dict)
                    or restoration.get("status") != "VERIFIED"
                    or restoration.get("verified") is not True):
                    reasons.append(f"{transport}: missing independently verified setup restoration")
            if data.get("status") != "PASS":
                reasons.append(f"{transport}: R0 comparison status is not PASS")
            for name in ("functional", "timing"):
                relative = f"{base}/candidate/r0_candidate_{name}.json"
                if data.get(f"candidate_{name}_sha256") != tracked[relative]:
                    reasons.append(f"{transport}: raw {name} SHA256 mismatch")
            baseline_ops = baseline_t.get("operations")
            candidate_ops = candidate_t.get("operations")
            if not isinstance(baseline_ops, dict) or not isinstance(candidate_ops, dict):
                reasons.append(f"{transport}: missing timing operations")
                continue
            for label, operations in (("baseline", baseline_ops), ("candidate", candidate_ops)):
                if operations.get("not_yet_covered"):
                    reasons.append(f"{transport}: {label} has unqualified operations")
                if not _operation_names(operations):
                    reasons.append(f"{transport}: {label} has zero timing coverage")
            shared = _operation_names(baseline_ops) & _operation_names(candidate_ops)
            unthresholded = shared - thresholds.keys()
            if unthresholded:
                reasons.append(f"{transport}: unthresholded operations {sorted(unthresholded)}")
            if _operation_names(baseline_ops) != _operation_names(candidate_ops):
                reasons.append(f"{transport}: missing/new timing operations")
            _validate_numeric_tree(baseline_ops)
            _validate_numeric_tree(candidate_ops)
            reasons.extend(_raw_timing_issues(baseline_ops, f"{transport}: baseline"))
            reasons.extend(_raw_timing_issues(candidate_ops, f"{transport}: candidate"))
            for label, operations in (("baseline", baseline_ops), ("candidate", candidate_ops)):
                for name in _operation_names(operations):
                    if name.startswith("waveform_acquisition."):
                        stats = operations["waveform_acquisition"][name.split(".", 1)[1]]
                    else:
                        stats = operations[name]
                    value = stats.get("p95")
                    if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
                        reasons.append(f"{transport}: invalid {label} p95 for {name}")
            functional_diffs = diff_functional(baseline_f, candidate_f)
            if functional_diffs:
                reasons.append(f"{transport}: {len(functional_diffs)} functional regressions")
            regressions, new, missing = diff_timing(baseline_ops, candidate_ops, thresholds)
            if new or missing or any(entry.regressed for entry in regressions):
                reasons.append(f"{transport}: independently confirmed timing/coverage regressions")
            if not regressions:
                reasons.append(f"{transport}: no timing comparisons")
            for field in ("identity_issues", "missing_operations", "unthresholded_operations",
                          "known_coverage_gaps", "functional_diffs", "timing_regressions"):
                if not isinstance(data.get(field), list):
                    reasons.append(f"{transport}: malformed comparison field {field}")
            if (data.get("identity_issues") or data.get("missing_operations")
                or data.get("unthresholded_operations") or data.get("known_coverage_gaps")
                or data.get("functional_diffs")):
                reasons.append(f"{transport}: comparison reports outstanding defects")
            reported = data.get("timing_regressions")
            if isinstance(reported, list):
                if len(reported) != len(regressions) or any(
                    not isinstance(item, dict) or item.get("operation") != actual.operation
                    or item.get("metric") != actual.metric
                    or item.get("regressed") != actual.regressed
                    for item, actual in zip(reported, regressions)
                ):
                    # The runner's dataclass serialization has no 'regressed' key:
                    # compare the independent booleans instead.
                    if len(reported) != len(regressions) or any(
                        not isinstance(item, dict) or item.get("operation") != actual.operation
                        or item.get("relative_exceeded") != actual.relative_exceeded
                        or item.get("absolute_exceeded") != actual.absolute_exceeded
                        for item, actual in zip(reported, regressions)
                    ):
                        reasons.append(f"{transport}: reported timing comparisons inconsistent")
        # Separately reviewed, cross-transport R0 rollup is mandatory.
        rollup = load("performance/transport_comparison/transport_comparison.json")
        if rollup.get("schema_version") != 1 or rollup.get("status") != "PASS":
            reasons.append("USB/TCPIP independently reviewed transport rollup not PASS")
        if rollup.get("threshold_sha256") != _sha(policy_path):
            reasons.append("R0 transport rollup threshold digest mismatch")
        approval = rollup.get("threshold_approval")
        if not isinstance(approval, dict) or approval.get("status") != "APPROVED":
            reasons.append("R0 baseline/threshold independent approval absent")
        artifact_hashes = rollup.get("artifacts_sha256")
        if not isinstance(artifact_hashes, dict):
            reasons.append("R0 transport rollup missing evidence digest map")
        else:
            for relative, recorded_sha in artifact_hashes.items():
                if not isinstance(relative, str) or not relative:
                    reasons.append("R0 transport rollup has invalid evidence path")
                    continue
                path = _track_file(root, f"performance/{relative}", tracked)
                if recorded_sha != _sha(path):
                    reasons.append(f"R0 transport artifact SHA256 mismatch: {relative}")
        for transport in ("usb", "tcpip"):
            extra = load(f"performance/{transport}/candidate/r0_extra_metrics.json")
            baseline_extra = load(f"performance/{transport}/baseline/r0_extra_metrics.json")
            for label, doc in (("candidate", extra), ("baseline", baseline_extra)):
                if not isinstance(doc.get("metrics"), dict) or not doc["metrics"]:
                    reasons.append(f"{transport}: {label} extra performance observations absent")
        return reasons

    def soak() -> list[str]:
        path = root / "soak"
        for name in ("soak_report.json", "soak_report.md"):
            evidence = _evidence_path(root, "soak/" + name)
            if not evidence.is_file():
                # The validator returns diagnostics for absent reports. For a
                # release gate, absence is pending work, not a failed run.
                raise FileNotFoundError(evidence)
        problems, digests = validate_soak_report(
            path, min_hours=24.0, expected_commit=commit
        )
        for typ, digest in digests.items():
            tracked[f"soak/soak_report.{ 'json' if typ == 'json' else 'md' }"] = digest
        return problems

    def a25() -> dict:
        qualification = load("a25/qualification.json")
        result = load("a25/hardware-cli-report.json")
        failed: list[str] = []
        blocked: list[str] = []
        if qualification.get("commit_sha") != commit:
            failed.append("A25 qualification commit mismatch")
        review_state = qualification.get("review_status")
        if review_state in (None, "PENDING", "NOT_RUN"):
            blocked.append("A25 independent review pending")
        elif review_state != "APPROVED":
            failed.append("A25 independent review rejected or malformed")
        installed = qualification.get("installed_cli")
        if installed is not True:
            (blocked if installed in (None, False) else failed).append(
                "Installed CLI not qualified"
            )
        released = qualification.get("session_released")
        if released is not True:
            (blocked if released is None else failed).append(
                "Independent post-job connection evidence absent or failed"
            )
        if result.get("commit_sha") != commit:
            failed.append("A25 installed CLI result commit mismatch")
        run_status = result.get("status")
        if run_status in (None, "not_run", "pending", "skipped"):
            blocked.append("A25 physical CLI run not executed")
        elif run_status != "pass" or result.get("exit_code") != 0:
            failed.append("A25 CLI hardware result not PASS")
        if "DPO4054" not in str(result.get("identity", "")).upper():
            (blocked if run_status in (None, "not_run", "pending", "skipped")
             else failed).append("A25 real scope identity missing")
        xml_path = _evidence_path(root, "a25/hardware-junit.xml")
        if not xml_path.is_file():
            blocked.append("A25 physical pytest JUnit missing")
        else:
            # Interpret the same bounded bytes as the retained digest; do not
            # hash and then reopen an attacker-controlled JUnit path.
            xml_raw = xml_path.read_bytes()
            if not 0 < len(xml_raw) <= 10_000_000:
                raise ValueError("A25 JUnit is empty or oversized")
            tracked[xml_path.relative_to(root).as_posix()] = hashlib.sha256(xml_raw).hexdigest()
            parsed_xml = ET.fromstring(xml_raw)
            suites = ([parsed_xml] if parsed_xml.tag == "testsuite"
                      else list(parsed_xml.findall("testsuite")))
            if not suites:
                failed.append("A25 JUnit has no test suite")
            elif (sum(int(s.get("tests", "0")) for s in suites) < 1
                  or not any(s.findall(".//testcase") for s in suites)):
                failed.append("A25 JUnit has no real hardware test cases")
            elif (any(int(s.get(field, "0")) for s in suites
                      for field in ("failures", "errors", "skipped"))
                  or any(s.findall(".//failure") or s.findall(".//error")
                         or s.findall(".//skipped") for s in suites)):
                failed.append("A25 physical pytest failures/errors/skips")
        return _findings(failed=failed, blocked=blocked)

    def review() -> dict:
        data = load("review.json")
        failed: list[str] = []
        blocked: list[str] = []
        if data.get("commit_sha") != commit:
            failed.append("Independent review applies to a different commit")
        status = data.get("status")
        if status in (None, "PENDING", "NOT_RUN"):
            blocked.append("Independent qualified human approval pending")
        elif status != "APPROVED":
            failed.append("Independent review rejected or malformed")
        else:
            if (not isinstance(data.get("reviewer"), str)
                or not data["reviewer"].strip()
                or not isinstance(data.get("approval_url"), str)
                or not data["approval_url"].startswith("https://github.com/")):
                failed.append("Independent human approval and traceable review URL required")
        if data.get("critical_open") is None or data.get("high_open") is None:
            blocked.append("Independent review finding counts pending")
        elif data.get("critical_open") != 0 or data.get("high_open") != 0:
            failed.append("Unresolved CRITICAL/HIGH review findings")
        return _findings(failed=failed, blocked=blocked)

    gates = {
        "P0-G0": _gate(software),
        "P0-G1": _gate(hardware),
        "P0-G2": _gate(performance),
        "P0-G3": _gate(soak),
        "P0-G4": _gate(a25),
        "REVIEW": _gate(review),
    }
    overall = (
        "PASS" if all(g["state"] == "PASS" for g in gates.values())
        else "FAIL" if any(g["state"] == "FAIL" for g in gates.values())
        else "BLOCKED"
    )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit_sha": commit,
        "overall": overall,
        "gates": gates,
        "artifacts_sha256": tracked,
        "notice": "Structural evidence review only; real hardware authenticity requires trusted bench review.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("qualification_reports"))
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()
    result = evaluate(args.root, commit=args.expected_commit)
    root = args.root
    _atomic_json(root / "manifest.json", result)
    _atomic_json(root / "summary.json", {
        "schema_version": 1, "commit_sha": result["commit_sha"],
        "status": result["overall"], "gates": result["gates"],
    })
    lines = ["# DPO4054 P0 release qualification", "",
             f"Commit: `{result['commit_sha']}`", "",
             f"Overall: **{result['overall']}**", ""]
    for name, gate in result["gates"].items():
        lines.append(f"## {name}: {gate['state']}")
        lines.extend(f"- {reason}" for reason in gate["reasons"])
        lines.append("")
    _atomic_text(root / "summary.md", "\n".join(lines) + "\n")
    for name, gate in result["gates"].items():
        print(f"{name}: {gate['state']}: {'; '.join(gate['reasons'])}")
    print(f"Release qualification: {result['overall']}")
    return 0 if result["overall"] == "PASS" else 1


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
