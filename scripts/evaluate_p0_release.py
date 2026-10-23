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
from pathlib import Path
from tempfile import NamedTemporaryFile
import xml.etree.ElementTree as ET

from validate_soak_report import validate_soak_report

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


def _load(path: Path, tracked: dict[str, str], root: Path) -> dict:
    # Reject traversal/symlinks into other paths. Evidence must be local to root.
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Evidence outside qualification root: {path}")
    raw = path.read_bytes()
    if not raw or len(raw) > 100_000_000:
        raise ValueError(f"Missing or excessive evidence size: {path}")
    payload = json.loads(raw.decode("utf-8"), parse_constant=lambda value: (
        _reject_constant(value)
    ))
    if not isinstance(payload, dict):
        raise ValueError(f"Evidence must be an object: {path}")
    tracked[str(path.relative_to(root))] = hashlib.sha256(raw).hexdigest()
    return payload


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
            if status == "SKIP":
                if not case.get("capability_absent") or not case.get("reason"):
                    reasons.append(f"Unsupported feature skip is not justified: {name}")
            elif status != "PASS":
                reasons.append(f"HIL case {name} not PASS: {status}")
            artifact = case.get("artifact")
            if not isinstance(artifact, str) or not artifact.strip():
                reasons.append(f"Missing retained case evidence path: {name}")
                continue
            # Track case evidence hashes; JSON documents are already checked
            # by their respective test runners and must be reviewed on the bench.
            path = (root / artifact).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                reasons.append(f"Missing/cross-root HIL artifact for {name}")
            else:
                tracked[str(path.relative_to(root))] = _sha(path)
        return reasons

    def performance() -> list[str]:
        reasons = []
        for transport in ("usb", "tcpip"):
            base = f"performance/{transport}"
            data = load(f"{base}/candidate/comparison_report.json")
            if data.get("status") != "PASS":
                reasons.append(f"{transport}: R0 candidate comparison not PASS")
            for field in (
                "identity_issues", "missing_operations", "unthresholded_operations",
                "known_coverage_gaps", "functional_diffs",
            ):
                if data.get(field):
                    reasons.append(f"{transport}: {field} is not empty")
            if any(item.get("regressed") for item in data.get("timing_regressions", [])):
                reasons.append(f"{transport}: p95 performance regression")
            for name in ("functional", "timing"):
                candidate_path = f"{base}/candidate/r0_candidate_{name}.json"
                baseline_path = f"{base}/baseline/r0_{name}_baseline.json"
                load(candidate_path)
                baseline = load(baseline_path)
                if baseline.get("commit_sha") in (None, "", "unknown"):
                    reasons.append(f"{transport}: missing approved baseline commit")
                digest = tracked[candidate_path]
                if data.get(f"candidate_{name}_sha256") != digest:
                    reasons.append(f"{transport}: candidate raw {name} SHA256 mismatch")
        return reasons

    def soak() -> list[str]:
        path = root / "soak"
        if not (path / "soak_report.json").is_file():
            raise FileNotFoundError(path / "soak_report.json")
        if not (path / "soak_report.md").is_file():
            raise FileNotFoundError(path / "soak_report.md")
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
        xml_path = root / "a25/hardware-junit.xml"
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
            elif any(int(s.get(field, "0")) for s in suites for field in ("failures", "errors")):
                reasons.append("A25 physical pytest failures/errors")
        return reasons

    def review() -> list[str]:
        data = load("review.json")
        issues = []
        if data.get("commit_sha") != commit:
            issues.append("Independent review applies to a different commit")
        if data.get("status") != "APPROVED" or not data.get("reviewer"):
            issues.append("Independent qualified reviewer has not signed off")
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
