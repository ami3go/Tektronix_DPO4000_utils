"""A18 evidence bundle creation and verification.

The ``.dpoe`` format is a ZIP container with a strict versioned manifest. The
manifest records SHA-256 and size for every payload. Bundles are written to a
same-directory temporary file, flushed/fsynced, then atomically finalized with
``os.replace`` so a failed/cancelled run cannot replace an existing bundle.
"""

from __future__ import annotations

from array import array
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import sys
import time
from typing import Any, Mapping, Sequence
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile

from .hardcopy import PNG_SIGNATURE
from .recipe import RecipeResult
from .rules import RuleEvaluation, RuleSetResult
from .waveform import WaveformData

EVIDENCE_SCHEMA = "dpo4000-evidence"
EVIDENCE_VERSION = 1
MAX_EVIDENCE_ARTIFACTS = 512
MAX_MANIFEST_BYTES = 1 * 1024 * 1024
MAX_ARTIFACT_BYTES = 1 * 1024 * 1024 * 1024
MAX_BUNDLE_UNCOMPRESSED_BYTES = 4 * 1024 * 1024 * 1024
MAX_METADATA_KEYS = 256
MAX_SEQUENCE_PREVIEW = 64
_HASH_CHUNK = 1024 * 1024


class EvidenceBundleError(RuntimeError):
    """Raised when an evidence bundle cannot be built or verified."""


class EvidenceBundleCancelled(EvidenceBundleError):
    """Raised when cooperative evidence generation is cancelled."""


@dataclass(frozen=True)
class EvidenceArtifact:
    path: str
    kind: str
    media_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class EvidenceBundleMetrics:
    total_s: float
    image_s: float
    waveform_s: float
    manifest_s: float
    finalize_s: float


@dataclass(frozen=True)
class EvidenceBundleResult:
    path: Path
    size_bytes: int
    sha256: str
    artifact_count: int
    metrics: EvidenceBundleMetrics


@dataclass(frozen=True)
class EvidenceVerification:
    path: Path
    artifact_count: int
    uncompressed_bytes: int
    bundle_sha256: str
    manifest: Mapping[str, Any]


def _check_cancel(cancel: Any) -> None:
    if cancel is None:
        return
    if callable(cancel):
        cancelled = bool(cancel())
    else:
        is_set = getattr(cancel, "is_set", None)
        cancelled = bool(is_set()) if callable(is_set) else bool(cancel)
    if cancelled:
        raise EvidenceBundleCancelled("Evidence bundle generation cancelled")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _iso_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _json_safe(value: Any, *, depth: int = 0) -> Any:
    if depth > 32:
        return {"type": type(value).__name__, "summary": "maximum serialization depth reached"}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return {"type": "float", "value": repr(value)}
        return value
    if isinstance(value, Enum):
        return _json_safe(value.value, depth=depth + 1)
    if isinstance(value, datetime):
        return _iso_datetime(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return {"type": "bytes", "size": len(value), "sha256": _sha256_bytes(value)}
    if isinstance(value, array):
        raw = value.tobytes()
        result: dict[str, Any] = {
            "type": "array",
            "typecode": value.typecode,
            "length": len(value),
            "sha256": _sha256_bytes(raw),
        }
        if len(value) <= MAX_SEQUENCE_PREVIEW:
            result["values"] = list(value)
        return result
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _json_safe(getattr(value, item.name), depth=depth + 1)
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        if len(value) > MAX_METADATA_KEYS:
            items = list(value.items())[:MAX_METADATA_KEYS]
            result = {
                str(key): _json_safe(item, depth=depth + 1) for key, item in items
            }
            result["__truncated_keys__"] = len(value) - len(items)
            return result
        return {
            str(key): _json_safe(item, depth=depth + 1) for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) <= MAX_SEQUENCE_PREVIEW:
            return [_json_safe(item, depth=depth + 1) for item in value]
        return {
            "type": type(value).__name__,
            "length": len(value),
            "preview": [
                _json_safe(item, depth=depth + 1)
                for item in value[:MAX_SEQUENCE_PREVIEW]
            ],
        }
    return {"type": type(value).__name__, "text": str(value)[:1024]}


def _recipe_result_mapping(result: RecipeResult) -> dict[str, Any]:
    return {
        "recipe_name": result.recipe_name,
        "state": result.state.value,
        "started_s": result.started_s,
        "finished_s": result.finished_s,
        "duration_s": result.duration_s,
        "error": result.error,
        "steps": [
            {
                "index": step.index,
                "name": step.name,
                "attempts": step.attempts,
                "started_s": step.started_s,
                "finished_s": step.finished_s,
                "duration_s": step.duration_s,
                "value": _json_safe(step.value),
            }
            for step in result.steps
        ],
    }


def _rule_evaluation_mapping(item: RuleEvaluation) -> dict[str, Any]:
    return {
        "rule_id": item.rule_id,
        "status": item.status.value,
        "timestamp": item.timestamp,
        "actual": item.actual,
        "expected": _json_safe(dict(item.expected)),
        "reason": item.reason,
        "children": [_rule_evaluation_mapping(child) for child in item.children],
    }


def _rule_result_mapping(result: RuleSetResult) -> dict[str, Any]:
    return {
        "name": result.name,
        "status": result.status.value,
        "timestamp": result.timestamp,
        "root": _rule_evaluation_mapping(result.root),
    }


def _json_bytes(value: Any) -> bytes:
    try:
        return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EvidenceBundleError(f"Evidence JSON serialization failed: {exc}") from exc


def _safe_member_path(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise EvidenceBundleError("Evidence artifact path must be non-empty")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or ".." in candidate.parts or "\\" in value:
        raise EvidenceBundleError(f"Unsafe evidence artifact path: {value!r}")
    normalized = str(candidate)
    if normalized in {".", "manifest.json"} or normalized.endswith("/"):
        raise EvidenceBundleError(f"Invalid evidence artifact path: {value!r}")
    return normalized


def _artifact_mapping(record: EvidenceArtifact) -> dict[str, Any]:
    return asdict(record)


def _write_artifact(
    archive: ZipFile,
    records: list[EvidenceArtifact],
    *,
    path: str,
    kind: str,
    media_type: str,
    data: bytes,
    cancel: Any,
) -> None:
    _check_cancel(cancel)
    member = _safe_member_path(path)
    if len(data) > MAX_ARTIFACT_BYTES:
        raise EvidenceBundleError(f"Evidence artifact {member!r} exceeds size limit")
    if any(record.path == member for record in records):
        raise EvidenceBundleError(f"Duplicate evidence artifact path: {member!r}")
    archive.writestr(member, data)
    records.append(
        EvidenceArtifact(
            path=member,
            kind=kind,
            media_type=media_type,
            size_bytes=len(data),
            sha256=_sha256_bytes(data),
        )
    )


def _waveform_index(waveforms: Mapping[str, WaveformData]) -> tuple[dict[str, Any], list[tuple[str, bytes]]]:
    items: list[dict[str, Any]] = []
    payloads: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    for key, waveform in waveforms.items():
        if not isinstance(waveform, WaveformData):
            raise EvidenceBundleError(f"Waveform {key!r} is not WaveformData")
        source = waveform.source.upper()
        if source in seen:
            raise EvidenceBundleError(f"Duplicate waveform source {source!r}")
        seen.add(source)
        raw_path = f"waveforms/{source}.raw"
        raw = waveform.samples.tobytes()
        payloads.append((raw_path, raw))
        items.append(
            {
                "source": waveform.source,
                "label": waveform.label,
                "start_index": waveform.start_index,
                "stop_index": waveform.stop_index,
                "requested_encoding": waveform.requested_encoding,
                "acquired_at": _iso_datetime(waveform.acquired_at),
                "sample_count": waveform.sample_count,
                "sample_typecode": waveform.samples.typecode,
                "sample_byteorder": sys.byteorder,
                "raw_path": raw_path,
                "preamble": _json_safe(waveform.preamble),
            }
        )
    return {"version": 1, "waveforms": items}, payloads


def create_evidence_bundle(
    path: str | Path,
    *,
    recipe_result: RecipeResult,
    rule_result: RuleSetResult | None = None,
    screen_png: bytes | None = None,
    waveforms: Mapping[str, WaveformData] | None = None,
    scope_identity: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    compressed: bool = True,
    cancel: Any = None,
) -> EvidenceBundleResult:
    """Create one atomic A18 evidence archive and return completion metrics."""
    if not isinstance(recipe_result, RecipeResult):
        raise EvidenceBundleError("recipe_result must be RecipeResult")
    if rule_result is not None and not isinstance(rule_result, RuleSetResult):
        raise EvidenceBundleError("rule_result must be RuleSetResult or None")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise EvidenceBundleError("metadata must be a mapping or None")
    if screen_png is not None:
        screen_png = bytes(screen_png)
        if not screen_png.startswith(PNG_SIGNATURE):
            raise EvidenceBundleError("screen_png is not a valid PNG payload")
    if waveforms is not None and not isinstance(waveforms, Mapping):
        raise EvidenceBundleError("waveforms must be a mapping or None")

    destination = Path(path)
    if destination.suffix.lower() != ".dpoe":
        destination = destination.with_suffix(".dpoe")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    compression = ZIP_DEFLATED if compressed else ZIP_STORED
    started = time.perf_counter()
    image_s = 0.0
    waveform_s = 0.0
    manifest_s = 0.0
    finalize_s = 0.0
    records: list[EvidenceArtifact] = []

    try:
        _check_cancel(cancel)
        with ZipFile(temporary, "w", compression=compression, compresslevel=6 if compressed else None) as archive:
            _write_artifact(
                archive,
                records,
                path="results/recipe_result.json",
                kind="recipe_result",
                media_type="application/json",
                data=_json_bytes(_recipe_result_mapping(recipe_result)),
                cancel=cancel,
            )
            if rule_result is not None:
                _write_artifact(
                    archive,
                    records,
                    path="results/rule_result.json",
                    kind="rule_result",
                    media_type="application/json",
                    data=_json_bytes(_rule_result_mapping(rule_result)),
                    cancel=cancel,
                )

            if screen_png is not None:
                image_started = time.perf_counter()
                _write_artifact(
                    archive,
                    records,
                    path="screen/scope.png",
                    kind="scope_screen",
                    media_type="image/png",
                    data=screen_png,
                    cancel=cancel,
                )
                image_s = time.perf_counter() - image_started

            if waveforms:
                waveform_started = time.perf_counter()
                index, payloads = _waveform_index(waveforms)
                _write_artifact(
                    archive,
                    records,
                    path="waveforms/index.json",
                    kind="waveform_index",
                    media_type="application/json",
                    data=_json_bytes(index),
                    cancel=cancel,
                )
                for raw_path, raw in payloads:
                    _write_artifact(
                        archive,
                        records,
                        path=raw_path,
                        kind="waveform_raw",
                        media_type="application/octet-stream",
                        data=raw,
                        cancel=cancel,
                    )
                waveform_s = time.perf_counter() - waveform_started

            if len(records) > MAX_EVIDENCE_ARTIFACTS:
                raise EvidenceBundleError(
                    f"Evidence bundle cannot exceed {MAX_EVIDENCE_ARTIFACTS} artifacts"
                )
            total_payload = sum(record.size_bytes for record in records)
            if total_payload > MAX_BUNDLE_UNCOMPRESSED_BYTES:
                raise EvidenceBundleError("Evidence bundle exceeds uncompressed size limit")

            manifest_started = time.perf_counter()
            manifest = {
                "schema": EVIDENCE_SCHEMA,
                "version": EVIDENCE_VERSION,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "scope_identity": None if scope_identity is None else str(scope_identity),
                "recipe_name": recipe_result.recipe_name,
                "recipe_state": recipe_result.state.value,
                "rule_status": None if rule_result is None else rule_result.status.value,
                "metadata": _json_safe(dict(metadata or {})),
                "artifacts": [_artifact_mapping(record) for record in records],
            }
            manifest_data = _json_bytes(manifest)
            if len(manifest_data) > MAX_MANIFEST_BYTES:
                raise EvidenceBundleError("Evidence manifest exceeds size limit")
            archive.writestr("manifest.json", manifest_data)
            manifest_s = time.perf_counter() - manifest_started

        _check_cancel(cancel)
        finalize_started = time.perf_counter()
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        try:
            directory_fd = os.open(str(destination.parent), os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finalize_s = time.perf_counter() - finalize_started
        total_s = time.perf_counter() - started
        return EvidenceBundleResult(
            path=destination,
            size_bytes=destination.stat().st_size,
            sha256=_sha256_file(destination),
            artifact_count=len(records),
            metrics=EvidenceBundleMetrics(
                total_s=total_s,
                image_s=image_s,
                waveform_s=waveform_s,
                manifest_s=manifest_s,
                finalize_s=finalize_s,
            ),
        )
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceBundleError(f"Duplicate JSON key in evidence manifest: {key!r}")
        result[key] = value
    return result


def _validate_manifest(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise EvidenceBundleError("Evidence manifest must be a JSON object")
    allowed = {
        "schema",
        "version",
        "created_at",
        "scope_identity",
        "recipe_name",
        "recipe_state",
        "rule_status",
        "metadata",
        "artifacts",
    }
    unknown = set(data) - allowed
    if unknown:
        raise EvidenceBundleError(f"Unknown evidence manifest fields: {sorted(unknown)!r}")
    if data.get("schema") != EVIDENCE_SCHEMA:
        raise EvidenceBundleError(f"Unsupported evidence schema: {data.get('schema')!r}")
    if data.get("version") != EVIDENCE_VERSION:
        raise EvidenceBundleError(f"Unsupported evidence version: {data.get('version')!r}")
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list):
        raise EvidenceBundleError("Evidence manifest artifacts must be a list")
    if len(artifacts) > MAX_EVIDENCE_ARTIFACTS:
        raise EvidenceBundleError("Evidence manifest contains too many artifacts")
    return data


def verify_evidence_bundle(path: str | Path) -> EvidenceVerification:
    """Verify manifest/member closure and SHA-256 integrity without extracting ZIP paths."""
    source = Path(path)
    if not source.is_file():
        raise EvidenceBundleError(f"Evidence bundle does not exist: {source}")
    try:
        with ZipFile(source, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise EvidenceBundleError("Evidence bundle contains duplicate ZIP members")
            if "manifest.json" not in names:
                raise EvidenceBundleError("Evidence bundle has no manifest.json")
            if len(infos) > MAX_EVIDENCE_ARTIFACTS + 1:
                raise EvidenceBundleError("Evidence bundle contains too many ZIP members")
            total_uncompressed = 0
            for info in infos:
                candidate = PurePosixPath(info.filename)
                if candidate.is_absolute() or ".." in candidate.parts or "\\" in info.filename:
                    raise EvidenceBundleError(f"Unsafe ZIP member path: {info.filename!r}")
                if info.is_dir():
                    raise EvidenceBundleError(f"Unexpected directory member: {info.filename!r}")
                if info.file_size > MAX_ARTIFACT_BYTES and info.filename != "manifest.json":
                    raise EvidenceBundleError(f"Evidence artifact is too large: {info.filename!r}")
                total_uncompressed += info.file_size
            if total_uncompressed > MAX_BUNDLE_UNCOMPRESSED_BYTES:
                raise EvidenceBundleError("Evidence bundle exceeds uncompressed size limit")
            manifest_info = archive.getinfo("manifest.json")
            if manifest_info.file_size > MAX_MANIFEST_BYTES:
                raise EvidenceBundleError("Evidence manifest exceeds size limit")
            manifest_raw = archive.read("manifest.json")
            try:
                manifest = json.loads(
                    manifest_raw.decode("utf-8"),
                    object_pairs_hook=_reject_duplicate_pairs,
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise EvidenceBundleError(f"Invalid evidence manifest JSON: {exc}") from exc
            manifest = _validate_manifest(manifest)

            expected_names = {"manifest.json"}
            seen_artifacts: set[str] = set()
            for entry in manifest["artifacts"]:
                if not isinstance(entry, dict):
                    raise EvidenceBundleError("Evidence artifact record must be an object")
                if set(entry) != {"path", "kind", "media_type", "size_bytes", "sha256"}:
                    raise EvidenceBundleError("Evidence artifact record has invalid fields")
                member = _safe_member_path(entry["path"])
                if member in seen_artifacts:
                    raise EvidenceBundleError(f"Duplicate manifest artifact: {member!r}")
                seen_artifacts.add(member)
                expected_names.add(member)
                if member not in names:
                    raise EvidenceBundleError(f"Manifest artifact is missing: {member!r}")
                expected_size = entry["size_bytes"]
                if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 0:
                    raise EvidenceBundleError(f"Invalid artifact size for {member!r}")
                digest_text = entry["sha256"]
                if not isinstance(digest_text, str) or len(digest_text) != 64:
                    raise EvidenceBundleError(f"Invalid SHA-256 for {member!r}")
                digest = hashlib.sha256()
                read_size = 0
                with archive.open(member, "r") as handle:
                    while True:
                        chunk = handle.read(_HASH_CHUNK)
                        if not chunk:
                            break
                        read_size += len(chunk)
                        digest.update(chunk)
                if read_size != expected_size:
                    raise EvidenceBundleError(
                        f"Artifact size mismatch for {member!r}: manifest={expected_size}, actual={read_size}"
                    )
                if digest.hexdigest() != digest_text.lower():
                    raise EvidenceBundleError(f"Artifact hash mismatch for {member!r}")

            extra = set(names) - expected_names
            if extra:
                raise EvidenceBundleError(f"Evidence bundle contains unmanifested members: {sorted(extra)!r}")
    except BadZipFile as exc:
        raise EvidenceBundleError(f"Invalid evidence ZIP archive: {exc}") from exc

    return EvidenceVerification(
        path=source,
        artifact_count=len(manifest["artifacts"]),
        uncompressed_bytes=total_uncompressed,
        bundle_sha256=_sha256_file(source),
        manifest=manifest,
    )


__all__ = [
    "EVIDENCE_SCHEMA",
    "EVIDENCE_VERSION",
    "EvidenceArtifact",
    "EvidenceBundleCancelled",
    "EvidenceBundleError",
    "EvidenceBundleMetrics",
    "EvidenceBundleResult",
    "EvidenceVerification",
    "create_evidence_bundle",
    "verify_evidence_bundle",
]
