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
from pathlib import Path
from tempfile import NamedTemporaryFile
import xml.etree.ElementTree as ET

from validate_soak_report import validate_soak_report
from dpo4000_utils.baseline_compare import diff_functional, diff_timing, load_thresholds

REQUIRED_CI = (
    "python_3_10", "python_3_11", "python_3_12", "python_3_13",
    "ruff", "pyside6", "codeql", "package_windows", "package_linux",
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
    relative = str(path.relative_to(root))
    path = _track_file(root, relative, tracked)
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=_reject_constant,
        object_pairs_hook=_unique_object,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"Evidence must be an object: {relative}")
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



def _reject_constant(token: str):
    raise ValueError(f"Nonstandard JSON number: {token}")


def _gate(fn) -> dict:
    try:
        reasons = fn()
    except FileNotFoundError as exc:
        return {"state": "BLOCKED", "reasons": [f"Missing evidence: {exc.filename or exc}"]}
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
        return {"state": "FAIL", "reasons": [f"Invalid evidence: {exc}"]}
    return {"state": "PASS" if not reasons else "FAIL", "reasons": reasons}


def evaluate(root: Path, *, commit: str) -> dict:
    """Evaluate all gates without opening an instrument session."""
    if len(commit) != 40 or any(ch not in "0123456789abcdef" for ch in commit.lower()):
        raise ValueError("--expected-commit must be an exact 40-digit Git SHA")
    if root.is_symlink():
        raise ValueError("Qualification evidence root must not be a symlink")
    root = root.resolve()
    tracked: dict[str, str] = {}

    def load(relative: str) -> dict:
        return _load(root / relative, tracked, root)

    def software() -> list[str]:
        data = load("software/ci.json")
        reasons = []
        if data.get("schema_version") != 1 or data.get("commit_sha") != commit:
            reasons.append("Software CI schema or commit mismatch")
        jobs = data.get("jobs", {})
        if not isinstance(jobs, dict):
            return [*reasons, "Missing CI jobs matrix"]
        for name in REQUIRED_CI:
            job = jobs.get(name)
            if not isinstance(job, dict) or job.get("status") != "PASS" or not job.get("url"):
                reasons.append(f"No successful traceable CI run: {name}")
        return reasons

    def hardware() -> list[str]:
        data = load("hardware/qualification.json")
        reasons = []
        if data.get("schema_version") != 1 or data.get("commit_sha") != commit:
            reasons.append("Hardware evidence schema or commit mismatch")
        if "DPO4054" not in str(data.get("idn", "")).upper():
            reasons.append("Missing real DPO4054 identity")
        if data.get("setup_restored") is not True:
            reasons.append("Initial instrument setup was not independently verified restored")
        cases = data.get("cases", [])
        if not isinstance(cases, list):
            return [*reasons, "Missing HIL feature cases"]
        by_name = {
            item["id"]: item for item in cases
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        for name in REQUIRED_HIL:
            case = by_name.get(name)
            if not case:
                reasons.append(f"Missing physical feature qualification: {name}")
                continue
            status = case.get("status")
            if status != "PASS":
                # All required feature IDs are mandatory. An unsupported capability
                # needs a separate approved exception, never an automatic PASS.
                reasons.append(f"HIL case {name} not PASS: {status}")
            artifact = case.get("artifact")
            if not isinstance(artifact, str) or not artifact.strip():
                reasons.append(f"Missing retained case evidence path: {name}")
                continue
            # Track case evidence hashes; JSON documents are already checked
            # by their respective test runners and must be reviewed on the bench.
            try:
                _track_file(root, artifact, tracked)
            except (FileNotFoundError, OSError, ValueError) as exc:
                reasons.append(f"Missing/unsafe HIL artifact for {name}: {exc}")
        return reasons

    def performance() -> list[str]:
        """Recompute regression decisions from raw evidence, never trust status alone."""
        reasons = []
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
        return reasons

    def soak() -> list[str]:
        path = root / "soak"
        for name in ("soak_report.json", "soak_report.md"):
            _evidence_path(root, "soak/" + name)
        problems, digests = validate_soak_report(
            path, min_hours=24.0, expected_commit=commit
        )
        for typ, digest in digests.items():
            tracked[f"soak/soak_report.{ 'json' if typ == 'json' else 'md' }"] = digest
        return problems

    def a25() -> list[str]:
        qualification = load("a25/qualification.json")
        result = load("a25/hardware-cli-report.json")
        reasons = []
        if qualification.get("commit_sha") != commit:
            reasons.append("A25 qualification commit mismatch")
        if qualification.get("review_status") != "APPROVED":
            reasons.append("A25 independent review not approved")
        if qualification.get("installed_cli") is not True:
            reasons.append("Installed CLI not qualified")
        if qualification.get("session_released") is not True:
            reasons.append("Independent post-job connection evidence absent")
        if result.get("status") != "pass" or result.get("exit_code") != 0:
            reasons.append("A25 CLI hardware result not PASS")
        if "DPO4054" not in str(result.get("identity", "")).upper():
            reasons.append("A25 real scope identity missing")
        xml_path = _evidence_path(root, "a25/hardware-junit.xml")
        if not xml_path.is_file():
            reasons.append("A25 physical pytest JUnit missing")
        else:
            tracked[str(xml_path.relative_to(root))] = _sha(xml_path)
            parsed = ET.parse(xml_path).getroot()
            suites = [parsed] if parsed.tag == "testsuite" else list(parsed.findall("testsuite"))
            if not suites:
                reasons.append("A25 JUnit has no test suite")
            elif sum(int(s.get("tests", "0")) for s in suites) < 1:
                reasons.append("A25 JUnit has no hardware test cases")
            elif (any(int(s.get(field, "0")) for s in suites
                      for field in ("failures", "errors", "skipped"))
                  or any(s.findall(".//failure") or s.findall(".//error")
                         or s.findall(".//skipped") for s in suites)):
                reasons.append("A25 physical pytest failures/errors/skips")
        return reasons

    def review() -> list[str]:
        data = load("review.json")
        issues = []
        if data.get("commit_sha") != commit:
            issues.append("Independent review applies to a different commit")
        if (data.get("status") != "APPROVED"
            or not isinstance(data.get("reviewer"), str)
            or not data["reviewer"].strip()
            or not isinstance(data.get("approval_url"), str)
            or not data["approval_url"].startswith("https://github.com/")):
            issues.append("Independent human approval and traceable review URL required")
        if data.get("critical_open") != 0 or data.get("high_open") != 0:
            issues.append("Unresolved CRITICAL/HIGH review findings")
        return issues

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
