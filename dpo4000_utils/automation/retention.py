"""Safe persistent A9 automation artifact retention.

The retention index is owner-namespaced so Automation and Logger can safely share
an output root. Deletion uses a two-step staging transaction: all candidate files
are atomically renamed into a private trash directory, the updated ownership
index is committed, and only then are staged files unlinked. Any failure before
the index commit rolls all staged files back to their original paths.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable

RETENTION_SCHEMA_VERSION = 1
RETENTION_INDEX_FILENAME = ".dpo4000-automation-retention-v1.json"
RETENTION_TRASH_DIRNAME = ".dpo4000-retention-trash"
DEFAULT_RETENTION_OWNER = "automation"
MAX_RETENTION_BYTES = 100 * 1024**4
MAX_RETENTION_AGE_S = 10 * 365 * 24 * 60 * 60.0


class RetentionError(RuntimeError):
    """Raised when retention ownership/safety validation fails."""


@dataclass(frozen=True)
class RetentionPolicy:
    keep_last_events: int | None = None
    max_bytes: int | None = None
    max_age_s: float | None = None
    min_free_bytes: int | None = None

    def __post_init__(self) -> None:
        if self.keep_last_events is not None:
            raw = self.keep_last_events
            if isinstance(raw, bool):
                raise ValueError("Retention event count must be a positive integer.")
            count = int(raw)
            if float(raw) != float(count) or count < 1:
                raise ValueError("Retention event count must be a positive integer.")
            object.__setattr__(self, "keep_last_events", count)
        for name in ("max_bytes", "min_free_bytes"):
            raw = getattr(self, name)
            if raw is None:
                continue
            if isinstance(raw, bool):
                raise ValueError(f"{name} must be a non-negative integer byte count.")
            value = int(raw)
            if float(raw) != float(value) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer byte count.")
            if value > MAX_RETENTION_BYTES:
                raise ValueError(f"{name} is unreasonably large.")
            object.__setattr__(self, name, value)
        if self.max_age_s is not None:
            value = float(self.max_age_s)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError("Retention age must be greater than zero.")
            if value > MAX_RETENTION_AGE_S:
                raise ValueError("Retention age must not exceed 10 years.")
            object.__setattr__(self, "max_age_s", value)

    @property
    def enabled(self) -> bool:
        return any(
            value is not None
            for value in (
                self.keep_last_events,
                self.max_bytes,
                self.max_age_s,
                self.min_free_bytes,
            )
        )


@dataclass(frozen=True)
class RetentionEvent:
    event_id: str
    completed_utc: str
    files: tuple[str, ...]
    owner: str = DEFAULT_RETENTION_OWNER


@dataclass(frozen=True)
class RetentionIndex:
    events: tuple[RetentionEvent, ...] = ()
    schema_version: int = RETENTION_SCHEMA_VERSION


@dataclass(frozen=True)
class RetentionDeletion:
    event_id: str
    files: tuple[str, ...]
    bytes: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RetentionPlan:
    root: str
    deletions: tuple[RetentionDeletion, ...] = ()
    tracked_events: int = 0
    tracked_bytes: int = 0
    bytes_to_reclaim: int = 0
    free_bytes: int = 0
    projected_free_bytes: int = 0
    satisfied: bool = True
    diagnostics: tuple[str, ...] = ()
    owner: str = DEFAULT_RETENTION_OWNER


@dataclass(frozen=True)
class RetentionApplyResult:
    deleted_events: int = 0
    deleted_files: int = 0
    reclaimed_bytes: int = 0


def _normalize_owner(owner: str) -> str:
    value = str(owner).strip().lower()
    if not value or not all(ch.isalnum() or ch in {"-", "_"} for ch in value):
        raise RetentionError(f"Invalid retention owner namespace: {owner!r}")
    return value


def _utc_iso(value: datetime | None = None) -> str:
    dt = value or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_utc(text: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(text))
    except ValueError as exc:
        raise RetentionError(f"Invalid retention event timestamp: {text!r}") from exc
    if dt.tzinfo is None:
        raise RetentionError("Retention event timestamps must include a timezone.")
    return dt.astimezone(timezone.utc)


def _root_path(root: str | Path, *, create: bool = False) -> Path:
    lexical = Path(root).expanduser()
    if create:
        lexical.mkdir(parents=True, exist_ok=True)
    if not lexical.exists() or not lexical.is_dir():
        raise RetentionError(f"Automation output root does not exist: {lexical}")
    return lexical.resolve()


def _validate_relative_text(relative: str) -> PurePosixPath:
    value = PurePosixPath(str(relative))
    if value.is_absolute() or not value.parts or any(part in {"", ".", ".."} for part in value.parts):
        raise RetentionError(f"Unsafe retention path: {relative!r}")
    if value.as_posix() == RETENTION_INDEX_FILENAME or value.parts[0] == RETENTION_TRASH_DIRNAME:
        raise RetentionError("Retention metadata/trash can never be owned as an artifact.")
    return value


def _lexical_index_path(root: Path, relative: str) -> Path:
    rel = _validate_relative_text(relative)
    lexical = root.joinpath(*rel.parts)
    resolved = lexical.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RetentionError(f"Retention path escapes automation root: {relative!r}") from exc
    return lexical


def _owned_relative_path(root: Path, artifact: str | Path) -> str:
    lexical = Path(artifact).expanduser()
    if lexical.is_symlink():
        raise RetentionError(f"Automation artifact may not be a symlink: {lexical}")
    resolved = lexical.resolve(strict=False)
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise RetentionError(f"Automation artifact is outside output root: {lexical}") from exc
    if not relative.parts:
        raise RetentionError("Automation output root itself cannot be registered as an artifact.")
    text = PurePosixPath(*relative.parts).as_posix()
    _validate_relative_text(text)
    return text


def _index_path(root: Path) -> Path:
    return root / RETENTION_INDEX_FILENAME


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def load_retention_index(root: str | Path) -> RetentionIndex:
    resolved_root = _root_path(root, create=True)
    path = _index_path(resolved_root)
    if not path.exists():
        return RetentionIndex()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RetentionError(f"Could not read retention index: {exc}") from exc
    if payload.get("schema_version") != RETENTION_SCHEMA_VERSION:
        raise RetentionError("Unsupported retention index schema version.")
    raw_events = payload.get("events")
    if not isinstance(raw_events, list):
        raise RetentionError("Retention index events must be a list.")
    events: list[RetentionEvent] = []
    seen_ids: set[tuple[str, str]] = set()
    seen_files: set[str] = set()
    for item in raw_events:
        if not isinstance(item, dict):
            raise RetentionError("Retention event entry must be an object.")
        owner = _normalize_owner(item.get("owner", DEFAULT_RETENTION_OWNER))
        event_id = str(item.get("event_id", "")).strip()
        identity = (owner, event_id)
        if not event_id or identity in seen_ids:
            raise RetentionError("Retention event IDs must be unique and non-empty within an owner.")
        completed = str(item.get("completed_utc", ""))
        _parse_utc(completed)
        raw_files = item.get("files")
        if not isinstance(raw_files, list) or not raw_files:
            raise RetentionError(f"Retention event {event_id!r} has no files.")
        files: list[str] = []
        for raw in raw_files:
            text = _validate_relative_text(str(raw)).as_posix()
            _lexical_index_path(resolved_root, text)
            if text in seen_files:
                raise RetentionError(f"Retention artifact is owned by multiple events: {text}")
            seen_files.add(text)
            files.append(text)
        seen_ids.add(identity)
        events.append(RetentionEvent(event_id, completed, tuple(files), owner))
    events.sort(key=lambda event: (_parse_utc(event.completed_utc), event.owner, event.event_id))
    return RetentionIndex(tuple(events))


def save_retention_index(root: str | Path, index: RetentionIndex) -> Path:
    resolved_root = _root_path(root, create=True)
    payload = {
        "schema_version": RETENTION_SCHEMA_VERSION,
        "events": [
            {
                "owner": event.owner,
                "event_id": event.event_id,
                "completed_utc": event.completed_utc,
                "files": list(event.files),
            }
            for event in index.events
        ],
    }
    target = _index_path(resolved_root)
    temporary = target.with_name(f"{target.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        _fsync_directory(resolved_root)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise RetentionError(f"Could not persist retention index: {exc}") from exc
    return target


def register_retention_event(
    root: str | Path,
    event_id: str,
    artifacts: Iterable[str | Path],
    *,
    completed_utc: datetime | None = None,
    owner: str = DEFAULT_RETENTION_OWNER,
) -> RetentionIndex:
    resolved_root = _root_path(root, create=True)
    namespace = _normalize_owner(owner)
    identifier = str(event_id).strip()
    if not identifier:
        raise ValueError("Retention event ID must not be empty.")
    index = load_retention_index(resolved_root)
    if any(event.owner == namespace and event.event_id == identifier for event in index.events):
        return index
    owned_elsewhere = {file for event in index.events for file in event.files}
    files: list[str] = []
    for artifact in artifacts:
        relative = _owned_relative_path(resolved_root, artifact)
        lexical = _lexical_index_path(resolved_root, relative)
        if not lexical.exists() or not lexical.is_file() or lexical.is_symlink():
            raise RetentionError(f"Completed automation artifact is not a regular file: {lexical}")
        if relative in owned_elsewhere:
            raise RetentionError(f"Automation artifact is already owned by another event: {relative}")
        if relative not in files:
            files.append(relative)
    if not files:
        raise RetentionError("A completed retention event must contain at least one artifact.")
    events = list(index.events)
    events.append(RetentionEvent(identifier, _utc_iso(completed_utc), tuple(files), namespace))
    events.sort(key=lambda event: (_parse_utc(event.completed_utc), event.owner, event.event_id))
    updated = RetentionIndex(tuple(events))
    save_retention_index(resolved_root, updated)
    return updated


def _event_size(root: Path, event: RetentionEvent) -> int:
    total = 0
    for relative in event.files:
        lexical = _lexical_index_path(root, relative)
        if lexical.is_symlink():
            raise RetentionError(f"Tracked artifact became a symlink: {lexical}")
        if lexical.exists():
            if not lexical.is_file():
                raise RetentionError(f"Tracked artifact is no longer a regular file: {lexical}")
            total += lexical.stat().st_size
    return total


def plan_retention(
    root: str | Path,
    policy: RetentionPolicy,
    *,
    protected_paths: Iterable[str | Path] = (),
    now_utc: datetime | None = None,
    free_bytes_override: int | None = None,
    owner: str = DEFAULT_RETENTION_OWNER,
) -> RetentionPlan:
    resolved_root = _root_path(root, create=True)
    namespace = _normalize_owner(owner)
    index = load_retention_index(resolved_root)
    events = [event for event in index.events if event.owner == namespace]
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    protected = {
        _owned_relative_path(resolved_root, path)
        for path in protected_paths
        if Path(path).exists()
    }
    event_sizes = {event.event_id: _event_size(resolved_root, event) for event in events}
    selected: dict[str, list[str]] = {}

    def can_delete(event: RetentionEvent) -> bool:
        return not any(file in protected for file in event.files)

    def select(event: RetentionEvent, reason: str) -> bool:
        if not can_delete(event):
            return False
        selected.setdefault(event.event_id, []).append(reason)
        return True

    if policy.max_age_s is not None:
        cutoff = now.timestamp() - policy.max_age_s
        for event in events:
            if _parse_utc(event.completed_utc).timestamp() < cutoff:
                select(event, "age")

    def remaining_events() -> list[RetentionEvent]:
        return [event for event in events if event.event_id not in selected]

    if policy.keep_last_events is not None:
        excess = max(0, len(remaining_events()) - policy.keep_last_events)
        for event in remaining_events():
            if excess <= 0:
                break
            if select(event, "count"):
                excess -= 1

    if policy.max_bytes is not None:
        current = sum(event_sizes[event.event_id] for event in remaining_events())
        for event in list(remaining_events()):
            if current <= policy.max_bytes:
                break
            if select(event, "size"):
                current -= event_sizes[event.event_id]

    if free_bytes_override is None:
        free_bytes = int(shutil.disk_usage(resolved_root).free)
    else:
        free_bytes = max(0, int(free_bytes_override))
    projected = free_bytes + sum(event_sizes[event_id] for event_id in selected)
    if policy.min_free_bytes is not None and projected < policy.min_free_bytes:
        for event in list(remaining_events()):
            if projected >= policy.min_free_bytes:
                break
            if select(event, "free-space"):
                projected += event_sizes[event.event_id]

    deletions = tuple(
        RetentionDeletion(
            event.event_id,
            event.files,
            event_sizes[event.event_id],
            tuple(dict.fromkeys(selected[event.event_id])),
        )
        for event in events
        if event.event_id in selected
    )
    remaining = [event for event in events if event.event_id not in selected]
    diagnostics: list[str] = []
    satisfied = True
    if policy.keep_last_events is not None and len(remaining) > policy.keep_last_events:
        satisfied = False
        diagnostics.append("Protected events prevent satisfying the event-count limit.")
    remaining_bytes = sum(event_sizes[event.event_id] for event in remaining)
    if policy.max_bytes is not None and remaining_bytes > policy.max_bytes:
        satisfied = False
        diagnostics.append("Protected events prevent satisfying the storage-size limit.")
    projected = free_bytes + sum(entry.bytes for entry in deletions)
    if policy.min_free_bytes is not None and projected < policy.min_free_bytes:
        satisfied = False
        diagnostics.append("Retention cannot reclaim enough space for the minimum-free-space guard.")
    return RetentionPlan(
        root=str(resolved_root),
        deletions=deletions,
        tracked_events=len(events),
        tracked_bytes=sum(event_sizes.values()),
        bytes_to_reclaim=sum(entry.bytes for entry in deletions),
        free_bytes=free_bytes,
        projected_free_bytes=projected,
        satisfied=satisfied,
        diagnostics=tuple(diagnostics),
        owner=namespace,
    )


def _remove_empty_parents(path: Path, stop: Path) -> None:
    current = path
    while current != stop:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def apply_retention_plan(root: str | Path, plan: RetentionPlan) -> RetentionApplyResult:
    resolved_root = _root_path(root, create=True)
    if str(resolved_root) != str(Path(plan.root).resolve()):
        raise RetentionError("Retention plan belongs to a different output root.")
    namespace = _normalize_owner(plan.owner)
    index = load_retention_index(resolved_root)
    by_id = {
        event.event_id: event
        for event in index.events
        if event.owner == namespace
    }

    selected: list[RetentionEvent] = []
    sources: list[tuple[Path, int]] = []
    for deletion in plan.deletions:
        event = by_id.get(deletion.event_id)
        if event is None or event.files != deletion.files:
            raise RetentionError("Retention index changed after preview; preview again before deleting.")
        selected.append(event)
        for relative in event.files:
            lexical = _lexical_index_path(resolved_root, relative)
            if lexical.is_symlink():
                raise RetentionError(f"Refusing to delete tracked symlink: {lexical}")
            if lexical.exists():
                if not lexical.is_file():
                    raise RetentionError(f"Refusing to delete non-file artifact: {lexical}")
                sources.append((lexical, lexical.stat().st_size))

    if not selected:
        return RetentionApplyResult()

    trash_root = resolved_root / RETENTION_TRASH_DIRNAME
    transaction = trash_root / uuid.uuid4().hex
    staged: list[tuple[Path, Path, int]] = []
    try:
        for source, size in sources:
            relative = source.relative_to(resolved_root)
            destination = transaction / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
            staged.append((source, destination, size))
        _fsync_directory(resolved_root)

        selected_ids = {event.event_id for event in selected}
        updated = RetentionIndex(
            tuple(
                event
                for event in index.events
                if not (event.owner == namespace and event.event_id in selected_ids)
            )
        )
        save_retention_index(resolved_root, updated)
    except BaseException as exc:
        rollback_errors: list[str] = []
        for source, destination, _size in reversed(staged):
            if not destination.exists():
                continue
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                os.replace(destination, source)
            except OSError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        _remove_empty_parents(transaction, trash_root)
        detail = f"Retention transaction failed and was rolled back: {exc}"
        if rollback_errors:
            detail += "; rollback errors: " + "; ".join(rollback_errors)
        raise RetentionError(detail) from exc

    cleanup_errors: list[str] = []
    reclaimed = 0
    deleted_files = 0
    for _source, destination, size in staged:
        try:
            destination.unlink(missing_ok=True)
            reclaimed += size
            deleted_files += 1
        except OSError as exc:
            cleanup_errors.append(f"{destination}: {exc}")
    _remove_empty_parents(transaction, trash_root)
    if cleanup_errors:
        raise RetentionError(
            "Retention index committed but trash cleanup was incomplete: " + "; ".join(cleanup_errors)
        )
    return RetentionApplyResult(
        deleted_events=len(selected),
        deleted_files=deleted_files,
        reclaimed_bytes=reclaimed,
    )


__all__ = [
    "DEFAULT_RETENTION_OWNER",
    "RETENTION_INDEX_FILENAME",
    "RETENTION_SCHEMA_VERSION",
    "RETENTION_TRASH_DIRNAME",
    "RetentionApplyResult",
    "RetentionDeletion",
    "RetentionError",
    "RetentionEvent",
    "RetentionIndex",
    "RetentionPlan",
    "RetentionPolicy",
    "apply_retention_plan",
    "load_retention_index",
    "plan_retention",
    "register_retention_event",
    "save_retention_index",
]
