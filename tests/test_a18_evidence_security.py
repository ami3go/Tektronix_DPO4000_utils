from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from dpo4000_utils.evidence import EvidenceBundleError, verify_evidence_bundle


def _manifest(artifacts: list[dict]) -> bytes:
    return (
        json.dumps(
            {
                "schema": "dpo4000-evidence",
                "version": 1,
                "created_at": "2026-09-27T00:00:00+00:00",
                "scope_identity": None,
                "recipe_name": "x",
                "recipe_state": "completed",
                "rule_status": None,
                "metadata": {},
                "artifacts": artifacts,
            }
        )
        + "\n"
    ).encode()


def test_path_traversal_member_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "traversal.dpoe"
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _manifest([]))
        archive.writestr("../escape.txt", b"bad")
    with pytest.raises(EvidenceBundleError, match="Unsafe ZIP member"):
        verify_evidence_bundle(path)


def test_unmanifested_payload_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "extra.dpoe"
    with ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", _manifest([]))
        archive.writestr("extra.bin", b"unexpected")
    with pytest.raises(EvidenceBundleError, match="unmanifested"):
        verify_evidence_bundle(path)


def test_duplicate_manifest_json_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-key.dpoe"
    raw = (
        '{"schema":"dpo4000-evidence","schema":"evil","version":1,'
        '"created_at":"x","scope_identity":null,"recipe_name":"x",'
        '"recipe_state":"completed","rule_status":null,"metadata":{},"artifacts":[]}'
    ).encode()
    with ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", raw)
    with pytest.raises(EvidenceBundleError, match="Duplicate JSON key"):
        verify_evidence_bundle(path)


def test_unknown_manifest_field_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "unknown.dpoe"
    document = json.loads(_manifest([]))
    document["python"] = "eval('no')"
    with ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(document).encode())
    with pytest.raises(EvidenceBundleError, match="Unknown evidence manifest fields"):
        verify_evidence_bundle(path)


def test_manifest_artifact_must_have_exact_fields(tmp_path: Path) -> None:
    path = tmp_path / "bad-record.dpoe"
    record = {
        "path": "result.json",
        "kind": "result",
        "media_type": "application/json",
        "size_bytes": 2,
        "sha256": "0" * 64,
        "exec": "bad",
    }
    with ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", _manifest([record]))
        archive.writestr("result.json", b"{}")
    with pytest.raises(EvidenceBundleError, match="invalid fields"):
        verify_evidence_bundle(path)


def test_manifest_cannot_reference_itself(tmp_path: Path) -> None:
    path = tmp_path / "self.dpoe"
    record = {
        "path": "manifest.json",
        "kind": "manifest",
        "media_type": "application/json",
        "size_bytes": 1,
        "sha256": "0" * 64,
    }
    with ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", _manifest([record]))
    with pytest.raises(EvidenceBundleError, match="Invalid evidence artifact path"):
        verify_evidence_bundle(path)
