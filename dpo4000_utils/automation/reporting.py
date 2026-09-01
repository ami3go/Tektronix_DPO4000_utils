"""Crash-tolerant Automation run/event reporting."""

from __future__ import annotations

import csv
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

AUTOMATION_REPORT_SCHEMA_VERSION = 1
_EVENT_COLUMNS = (
    "event_id",
    "started_utc",
    "ended_utc",
    "description",
    "cause",
    "status",
    "elapsed_s",
    "retry_count",
    "artifact_paths",
    "error_class",
    "error_text",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


@dataclass(frozen=True)
class AutomationEventRecord:
    event_id: str
    started_utc: str
    ended_utc: str
    description: str
    cause: str
    status: str
    elapsed_s: float
    retry_count: int = 0
    artifact_paths: tuple[str, ...] = ()
    error_class: str = ""
    error_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["artifact_paths"] = list(self.artifact_paths)
        return payload


@dataclass
class AutomationRunReporter:
    """Append event records immediately and write one atomic final run summary."""

    root: Path
    mode: str
    config: Mapping[str, Any]
    resource: str = ""
    idn: str = ""
    profile_name: str = ""
    package_version: str = ""
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        self.root = Path(self.root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        stamp = self.started_at.strftime("%Y%m%dT%H%M%S.%fZ")
        stem = f"automation_{stamp}_{self.run_id[:8]}"
        self.event_jsonl_path = self.root / f"{stem}.events.jsonl"
        self.event_csv_path = self.root / f"{stem}.events.csv"
        self.summary_path = self.root / f"{stem}.summary.json"
        self.event_count = 0
        self._finalized = False
        self._write_csv_header()

    def _write_csv_header(self) -> None:
        with self.event_csv_path.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=_EVENT_COLUMNS)
            writer.writeheader()
            handle.flush()
            os.fsync(handle.fileno())

    @property
    def finalized(self) -> bool:
        return self._finalized

    def append_event(self, event: AutomationEventRecord) -> None:
        """Durably append one event to JSONL and CSV before returning."""
        if self._finalized:
            raise RuntimeError("Automation report is already finalized.")
        payload = event.to_dict()
        with self.event_jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, allow_nan=False))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        csv_payload = dict(payload)
        csv_payload["artifact_paths"] = json.dumps(payload["artifact_paths"], separators=(",", ":"))
        with self.event_csv_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=_EVENT_COLUMNS)
            writer.writerow(csv_payload)
            handle.flush()
            os.fsync(handle.fileno())
        self.event_count += 1

    def finalize(
        self,
        *,
        stop_reason: str,
        counters: Mapping[str, Any],
        recovery: Mapping[str, Any] | None = None,
        retention: Mapping[str, Any] | None = None,
        final_error: str = "",
        ended_at: datetime | None = None,
    ) -> Path:
        """Write an idempotent atomic summary. Event files remain independently readable."""
        if self._finalized:
            return self.summary_path
        ended = ended_at or _utc_now()
        elapsed = max(0.0, (ended - self.started_at).total_seconds())
        summary = {
            "schema_version": AUTOMATION_REPORT_SCHEMA_VERSION,
            "run_id": self.run_id,
            "package_version": self.package_version,
            "profile_name": self.profile_name,
            "mode": self.mode,
            "resource": self.resource,
            "idn": self.idn,
            "started_utc": _iso(self.started_at),
            "ended_utc": _iso(ended),
            "elapsed_s": elapsed,
            "stop_reason": str(stop_reason),
            "final_error": str(final_error),
            "event_count": self.event_count,
            "event_jsonl": self.event_jsonl_path.name,
            "event_csv": self.event_csv_path.name,
            "counters": dict(counters),
            "recovery": dict(recovery or {}),
            "retention": dict(retention or {}),
            "config": dict(self.config),
        }
        _atomic_json(self.summary_path, summary)
        self._finalized = True
        return self.summary_path


def make_event_record(
    *,
    sequence: int,
    description: str,
    cause: str,
    status: str,
    started_at: datetime,
    ended_at: datetime,
    retry_count: int = 0,
    artifact_paths: tuple[str, ...] = (),
    error: BaseException | None = None,
    error_text: str = "",
) -> AutomationEventRecord:
    elapsed = max(0.0, (ended_at - started_at).total_seconds())
    return AutomationEventRecord(
        event_id=f"event-{int(sequence):08d}",
        started_utc=_iso(started_at),
        ended_utc=_iso(ended_at),
        description=str(description),
        cause=str(cause),
        status=str(status),
        elapsed_s=elapsed,
        retry_count=max(0, int(retry_count)),
        artifact_paths=tuple(str(path) for path in artifact_paths),
        error_class=error.__class__.__name__ if error is not None else "",
        error_text=str(error) if error is not None else str(error_text),
    )


__all__ = [
    "AUTOMATION_REPORT_SCHEMA_VERSION",
    "AutomationEventRecord",
    "AutomationRunReporter",
    "make_event_record",
]
