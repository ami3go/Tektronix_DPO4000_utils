"""Configurable flush/fsync policy for sustained Logger text output."""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


@dataclass(frozen=True)
class CsvSyncPolicy:
    """Bounded durability policy for append-only CSV segments.

    ``flush_every_records`` controls Python/stdio flushing. ``fsync_every_records``
    and ``fsync_interval_s`` bound how long records may remain only in the OS page
    cache. ``fsync_on_close`` ensures a clean segment close is durable.
    """

    flush_every_records: int = 1
    fsync_every_records: int = 50
    fsync_interval_s: float = 5.0
    fsync_on_close: bool = True

    def __post_init__(self) -> None:
        for name in ("flush_every_records", "fsync_every_records"):
            raw = getattr(self, name)
            if isinstance(raw, bool):
                raise ValueError(f"{name} must be a positive integer.")
            value = int(raw)
            if float(raw) != float(value) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")
            object.__setattr__(self, name, value)
        interval = float(self.fsync_interval_s)
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("fsync_interval_s must be a positive finite number.")
        if not isinstance(self.fsync_on_close, bool):
            raise ValueError("fsync_on_close must be boolean.")
        object.__setattr__(self, "fsync_interval_s", interval)


class CsvSyncController:
    """Track record flush/sync cadence for one open text file."""

    def __init__(
        self,
        handle: TextIO,
        path: str | Path,
        policy: CsvSyncPolicy | None = None,
    ) -> None:
        self.handle = handle
        self.path = Path(path)
        self.policy = policy or CsvSyncPolicy()
        self.records = 0
        self.last_fsync_monotonic = time.monotonic()
        self.bytes_written = 0

    def _refresh_size(self) -> None:
        try:
            self.bytes_written = self.path.stat().st_size
        except OSError:
            self.bytes_written = 0

    def force(self) -> int:
        """Flush and fsync immediately, returning current file size."""
        self.handle.flush()
        os.fsync(self.handle.fileno())
        self.last_fsync_monotonic = time.monotonic()
        self._refresh_size()
        return self.bytes_written

    def after_record(self) -> int:
        """Apply configured post-record flush/fsync policy."""
        self.records += 1
        if self.records % self.policy.flush_every_records == 0:
            self.handle.flush()
        now = time.monotonic()
        if (
            self.records % self.policy.fsync_every_records == 0
            or now - self.last_fsync_monotonic >= self.policy.fsync_interval_s
        ):
            self.handle.flush()
            os.fsync(self.handle.fileno())
            self.last_fsync_monotonic = now
        self._refresh_size()
        return self.bytes_written

    def close(self) -> int:
        """Apply final durability policy before the owner closes the handle."""
        self.handle.flush()
        if self.policy.fsync_on_close:
            os.fsync(self.handle.fileno())
            self.last_fsync_monotonic = time.monotonic()
        self._refresh_size()
        return self.bytes_written


__all__ = ["CsvSyncController", "CsvSyncPolicy"]
