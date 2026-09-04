"""Crash-tolerant Logger run reporting.

Logger reports deliberately use sparse durable events plus atomic cumulative
checkpoints rather than fsyncing one report row for every high-rate waveform
record. The data files remain the source of individual samples/records; this
module summarizes the sustained run and preserves the latest counters if the
process or host stops before normal finalization.
"""

from __future__ import annotations

import csv
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

LOGGER_REPORT_SCHEMA_VERSION = 1
_EVENT_COLUMNS = (
    "timestamp_utc",
    "timestamp_local",
    "event_type",
    "sequence",
    "details",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _iso_local(value: datetime) -> str:
    return value.astimezone().isoformat()


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


@dataclass
class LoggerRunReporter:
    """Write sparse durable events, cumulative checkpoints and one final summary."""

    root: Path
    config: Mapping[str, Any]
    package_version: str = ""
    profile_name: str = ""
    resource: str = ""
    idn: str = ""
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        self.root = Path(self.root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        stamp = self.started_at.strftime("%Y%m%dT%H%M%S.%fZ")
        stem = f"logger_run_{stamp}_{self.run_id[:8]}"
        self.event_jsonl_path = self.root / f"{stem}.events.jsonl"
        self.event_csv_path = self.root / f"{stem}.events.csv"
        self.checkpoint_path = self.root / f"{stem}.checkpoint.json"
        self.summary_path = self.root / f"{stem}.summary.json"
        self.event_count = 0
        self._finalized = False
        self._write_csv_header()

    @property
    def finalized(self) -> bool:
        return self._finalized

    def _write_csv_header(self) -> None:
        with self.event_csv_path.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=_EVENT_COLUMNS)
            writer.writeheader()
            handle.flush()
            os.fsync(handle.fileno())

    def append_event(
        self,
        event_type: str,
        *,
        sequence: int | None = None,
        details: Mapping[str, Any] | None = None,
        at: datetime | None = None,
    ) -> None:
        """Durably append one low-frequency run lifecycle event.

        JSONL is authoritative. Once its fsync succeeds, ``event_count`` is
        advanced even if the secondary convenience CSV write subsequently
        fails. This keeps later checkpoints/final summaries consistent with
        the durable event source.
        """
        if self._finalized:
            raise RuntimeError("Logger report is already finalized.")
        moment = at or _utc_now()
        payload = {
            "timestamp_utc": _iso_utc(moment),
            "timestamp_local": _iso_local(moment),
            "event_type": str(event_type),
            "sequence": None if sequence is None else int(sequence),
            "details": dict(details or {}),
        }
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
        with self.event_jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.event_count += 1

        csv_payload = dict(payload)
        csv_payload["details"] = json.dumps(
            payload["details"], sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        with self.event_csv_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=_EVENT_COLUMNS)
            writer.writerow(csv_payload)
            handle.flush()
            os.fsync(handle.fileno())

    def _common_payload(self) -> dict[str, Any]:
        return {
            "schema_version": LOGGER_REPORT_SCHEMA_VERSION,
            "run_id": self.run_id,
            "package_version": str(self.package_version),
            "profile_name": str(self.profile_name),
            "resource": str(self.resource),
            "idn": str(self.idn),
            "started_utc": _iso_utc(self.started_at),
            "started_local": _iso_local(self.started_at),
            "event_count": self.event_count,
            "event_jsonl": self.event_jsonl_path.name,
            "event_csv": self.event_csv_path.name,
            "checkpoint_json": self.checkpoint_path.name,
            "config": dict(self.config),
        }

    def checkpoint(
        self,
        state: Mapping[str, Any],
        *,
        reason: str = "periodic",
        at: datetime | None = None,
    ) -> Path:
        """Atomically replace the cumulative crash-recovery checkpoint."""
        if self._finalized:
            return self.checkpoint_path
        moment = at or _utc_now()
        payload = self._common_payload()
        payload.update(
            {
                "status": "checkpoint",
                "checkpoint_reason": str(reason),
                "updated_utc": _iso_utc(moment),
                "updated_local": _iso_local(moment),
                "elapsed_s": max(0.0, (moment - self.started_at).total_seconds()),
                "state": dict(state),
            }
        )
        _atomic_json(self.checkpoint_path, payload)
        return self.checkpoint_path

    def finalize(
        self,
        *,
        stop_reason: str,
        state: Mapping[str, Any],
        final_error: str = "",
        ended_at: datetime | None = None,
    ) -> Path:
        """Write an idempotent final JSON summary after the writer is closed."""
        if self._finalized:
            return self.summary_path
        ended = ended_at or _utc_now()
        payload = self._common_payload()
        payload.update(
            {
                "status": "final",
                "ended_utc": _iso_utc(ended),
                "ended_local": _iso_local(ended),
                "elapsed_s": max(0.0, (ended - self.started_at).total_seconds()),
                "stop_reason": str(stop_reason),
                "final_error": str(final_error),
                "state": dict(state),
            }
        )
        _atomic_json(self.summary_path, payload)
        self._finalized = True
        return self.summary_path


__all__ = ["LOGGER_REPORT_SCHEMA_VERSION", "LoggerRunReporter"]
