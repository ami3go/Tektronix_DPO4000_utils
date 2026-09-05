"""Bounded Logger producer/writer queue and dedicated filesystem writer thread."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from threading import Condition, Event, Thread
from typing import Any

from .models import LoggerRecord


@dataclass(frozen=True)
class BufferPolicy:
    """Hard queue bounds for sustained Logger operation."""

    max_records: int = 8
    max_bytes: int = 256 * 1024 * 1024
    stop_after_overflows: int = 5

    def __post_init__(self) -> None:
        for name in ("max_records", "max_bytes", "stop_after_overflows"):
            raw = getattr(self, name)
            if isinstance(raw, bool):
                raise ValueError(f"{name} must be a positive integer.")
            value = int(raw)
            if float(raw) != float(value) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")
            object.__setattr__(self, name, value)


@dataclass(frozen=True)
class BufferSnapshot:
    queued_records: int = 0
    queued_bytes: int = 0
    inflight_records: int = 0
    inflight_bytes: int = 0
    peak_records: int = 0
    peak_bytes: int = 0
    enqueued_records: int = 0
    written_records: int = 0
    dropped_records: int = 0
    write_failed_records: int = 0
    overflow_events: int = 0
    consecutive_overflows: int = 0
    bytes_written: int = 0
    last_write_s: float = 0.0
    total_write_s: float = 0.0
    segment_index: int = 0
    rotation_count: int = 0
    current_segment_bytes: int = 0
    output_paths: tuple[str, ...] = ()
    error: str = ""
    accepting: bool = False
    stopped: bool = False


class BoundedRecordBuffer:
    """FIFO buffer bounded across queued plus writer-inflight records.

    A record moves into an explicit in-flight reservation before filesystem I/O.
    Its memory remains charged against the hard bounds until the write succeeds or
    fails, so persistence failures and forced stops cannot create unaccounted data.
    """

    def __init__(self, policy: BufferPolicy) -> None:
        self.policy = policy
        self._items: deque[tuple[LoggerRecord, int]] = deque()
        self._inflight: tuple[LoggerRecord, int] | None = None
        self._bytes = 0
        self._peak_records = 0
        self._peak_bytes = 0
        self._enqueued = 0
        self._dropped = 0
        self._write_failed = 0
        self._overflow_events = 0
        self._consecutive_overflows = 0

    @property
    def queued_records(self) -> int:
        return len(self._items)

    @property
    def inflight_records(self) -> int:
        return 1 if self._inflight is not None else 0

    @property
    def resident_records(self) -> int:
        return self.queued_records + self.inflight_records

    @property
    def queued_bytes(self) -> int:
        if self._inflight is None:
            return self._bytes
        return self._bytes - self._inflight[1]

    @property
    def inflight_bytes(self) -> int:
        return 0 if self._inflight is None else self._inflight[1]

    @property
    def resident_bytes(self) -> int:
        return self._bytes

    @property
    def peak_records(self) -> int:
        return self._peak_records

    @property
    def peak_bytes(self) -> int:
        return self._peak_bytes

    @property
    def enqueued_records(self) -> int:
        return self._enqueued

    @property
    def dropped_records(self) -> int:
        return self._dropped

    @property
    def write_failed_records(self) -> int:
        return self._write_failed

    @property
    def overflow_events(self) -> int:
        return self._overflow_events

    @property
    def consecutive_overflows(self) -> int:
        return self._consecutive_overflows

    def has_capacity(self) -> bool:
        return self.resident_records < self.policy.max_records and self._bytes < self.policy.max_bytes

    def try_put(self, record: LoggerRecord) -> bool:
        size = max(1, int(record.estimated_bytes))
        if (
            self.resident_records >= self.policy.max_records
            or self._bytes + size > self.policy.max_bytes
        ):
            self._dropped += 1
            self._overflow_events += 1
            self._consecutive_overflows += 1
            return False
        self._items.append((record, size))
        self._bytes += size
        self._enqueued += 1
        self._consecutive_overflows = 0
        self._peak_records = max(self._peak_records, self.resident_records)
        self._peak_bytes = max(self._peak_bytes, self._bytes)
        return True

    def take_left(self) -> LoggerRecord | None:
        if self._inflight is not None:
            raise RuntimeError("A Logger record is already in flight.")
        if not self._items:
            return None
        self._inflight = self._items.popleft()
        return self._inflight[0]

    def commit_inflight(self) -> None:
        if self._inflight is None:
            raise RuntimeError("No Logger record is in flight.")
        _record, size = self._inflight
        self._bytes -= size
        self._inflight = None

    def fail_inflight(self) -> None:
        if self._inflight is None:
            return
        _record, size = self._inflight
        self._bytes -= size
        self._inflight = None
        self._dropped += 1
        self._write_failed += 1

    def pop_left(self) -> LoggerRecord | None:
        """Compatibility helper: take then immediately commit one record."""
        record = self.take_left()
        if record is not None:
            self.commit_inflight()
        return record

    def discard_all(self) -> int:
        count = len(self._items)
        removed_bytes = sum(size for _record, size in self._items)
        self._items.clear()
        self._bytes -= removed_bytes
        self._dropped += count
        return count


class LoggerWriterWorker:
    """Own output writers on one dedicated daemon thread and drain a bounded queue."""

    def __init__(
        self,
        output_factory: Callable[[], Any],
        policy: BufferPolicy,
        *,
        after_write: Callable[[Any], None] | None = None,
        after_close: Callable[[Any], None] | None = None,
    ) -> None:
        self._output_factory = output_factory
        self.policy = policy
        self._after_write = after_write
        self._after_close = after_close
        self._buffer = BoundedRecordBuffer(policy)
        self._condition = Condition()
        self._ready = Event()
        self._stopped = Event()
        self._stop_requested = False
        self._drain_on_stop = True
        self._accepting = True
        self._error: BaseException | None = None
        self._written_records = 0
        self._bytes_written = 0
        self._last_write_s = 0.0
        self._total_write_s = 0.0
        self._segment_index = 0
        self._rotation_count = 0
        self._current_segment_bytes = 0
        self._output_paths: tuple[str, ...] = ()
        self._thread = Thread(
            target=self._run,
            name="DPO4000-LoggerWriter",
            daemon=True,
        )

    @property
    def error(self) -> BaseException | None:
        with self._condition:
            return self._error

    @property
    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def start(self, *, ready_timeout_s: float = 5.0) -> None:
        self._thread.start()
        if not self._ready.wait(max(0.1, float(ready_timeout_s))):
            self.request_stop(drain=False)
            raise TimeoutError("Logger writer thread did not initialize in time.")
        error = self.error
        if error is not None:
            raise RuntimeError(f"Logger writer could not initialize: {error}") from error

    def has_capacity(self) -> bool:
        with self._condition:
            return self._accepting and self._error is None and self._buffer.has_capacity()

    def try_enqueue(self, record: LoggerRecord) -> bool:
        with self._condition:
            if not self._accepting or self._error is not None:
                return False
            accepted = self._buffer.try_put(record)
            if accepted:
                self._condition.notify()
            return accepted

    def request_stop(self, *, drain: bool = True) -> None:
        with self._condition:
            self._accepting = False
            self._stop_requested = True
            self._drain_on_stop = bool(drain)
            if not drain:
                self._buffer.discard_all()
            self._condition.notify_all()

    def wait(self, timeout_s: float | None = None) -> bool:
        return self._stopped.wait(timeout_s)

    def snapshot(self) -> BufferSnapshot:
        with self._condition:
            return BufferSnapshot(
                queued_records=self._buffer.queued_records,
                queued_bytes=self._buffer.queued_bytes,
                inflight_records=self._buffer.inflight_records,
                inflight_bytes=self._buffer.inflight_bytes,
                peak_records=self._buffer.peak_records,
                peak_bytes=self._buffer.peak_bytes,
                enqueued_records=self._buffer.enqueued_records,
                written_records=self._written_records,
                dropped_records=self._buffer.dropped_records,
                write_failed_records=self._buffer.write_failed_records,
                overflow_events=self._buffer.overflow_events,
                consecutive_overflows=self._buffer.consecutive_overflows,
                bytes_written=self._bytes_written,
                last_write_s=self._last_write_s,
                total_write_s=self._total_write_s,
                segment_index=self._segment_index,
                rotation_count=self._rotation_count,
                current_segment_bytes=self._current_segment_bytes,
                output_paths=self._output_paths,
                error=str(self._error) if self._error is not None else "",
                accepting=self._accepting,
                stopped=self._stopped.is_set(),
            )

    def _update_output_snapshot_locked(self, output: Any) -> None:
        self._bytes_written = int(getattr(output, "bytes_written", 0))
        self._segment_index = int(getattr(output, "segment_index", 0))
        self._rotation_count = int(getattr(output, "rotation_count", 0))
        self._current_segment_bytes = int(getattr(output, "current_segment_bytes", 0))
        self._output_paths = tuple(str(path) for path in getattr(output, "current_paths", ()))

    def _set_error_locked(self, exc: BaseException, *, fail_inflight: bool = False) -> None:
        if fail_inflight:
            self._buffer.fail_inflight()
        if self._error is None:
            self._error = exc
        self._accepting = False
        self._stop_requested = True
        self._drain_on_stop = False
        self._buffer.discard_all()
        self._condition.notify_all()

    def _next_record(self) -> LoggerRecord | None:
        with self._condition:
            while not self._buffer.queued_records and not self._stop_requested:
                self._condition.wait(timeout=0.5)
            if self._buffer.queued_records:
                return self._buffer.take_left()
            return None

    def _run(self) -> None:
        output = None
        try:
            output = self._output_factory()
            with self._condition:
                self._update_output_snapshot_locked(output)
            self._ready.set()

            while True:
                record = self._next_record()
                if record is None:
                    with self._condition:
                        if self._stop_requested and (
                            not self._drain_on_stop or not self._buffer.queued_records
                        ):
                            break
                    continue

                started = time.monotonic()
                try:
                    output.append(record)
                except BaseException as exc:  # noqa: BLE001 - writer must fail closed.
                    with self._condition:
                        self._set_error_locked(exc, fail_inflight=True)
                    break

                elapsed = max(0.0, time.monotonic() - started)
                with self._condition:
                    self._buffer.commit_inflight()
                    self._written_records += 1
                    self._last_write_s = elapsed
                    self._total_write_s += elapsed
                    self._update_output_snapshot_locked(output)

                if self._after_write is not None:
                    try:
                        self._after_write(output)
                    except BaseException as exc:  # noqa: BLE001 - record itself is already durable.
                        with self._condition:
                            self._set_error_locked(exc)
                        break
        except BaseException as exc:  # noqa: BLE001 - startup failures are reported.
            with self._condition:
                self._set_error_locked(exc, fail_inflight=True)
            self._ready.set()
        finally:
            if output is not None:
                try:
                    output.close()
                    if self._after_close is not None:
                        self._after_close(output)
                    with self._condition:
                        self._update_output_snapshot_locked(output)
                except BaseException as exc:  # noqa: BLE001
                    with self._condition:
                        self._set_error_locked(exc, fail_inflight=True)
            self._ready.set()
            self._stopped.set()


__all__ = [
    "BoundedRecordBuffer",
    "BufferPolicy",
    "BufferSnapshot",
    "LoggerWriterWorker",
]
