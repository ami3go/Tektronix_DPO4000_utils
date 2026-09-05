"""Logger output-session multiplexer with complete-record segment rotation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .bus_csv import BusCsvStreamWriter
from .csv_stream import WaveformCsvStreamWriter
from .dpo4log import Dpo4LogWriter
from .measurement_csv import MeasurementCsvStreamWriter
from .mixed_csv import MixedCsvStreamWriter
from .models import LoggerMode, LoggerOutputFormat, LoggerRecord
from .rotation import RotationPolicy
from .sync import CsvSyncPolicy


class LoggerOutputSession:
    """Own one Logger run and rotate writers only between complete records."""

    def __init__(
        self,
        root: str | Path,
        output_format: LoggerOutputFormat,
        *,
        mode: LoggerMode = LoggerMode.WAVEFORM,
        measurement_slots: tuple[int, ...] = (),
        run_metadata: Mapping[str, Any] | None = None,
        rotation_policy: RotationPolicy | None = None,
        csv_sync_policy: CsvSyncPolicy | None = None,
    ) -> None:
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self.output_format = LoggerOutputFormat(output_format)
        self.mode = LoggerMode(mode)
        self.measurement_slots = tuple(measurement_slots)
        self.run_metadata = dict(run_metadata or {})
        self.rotation_policy = rotation_policy or RotationPolicy()
        self.csv_sync_policy = csv_sync_policy or CsvSyncPolicy()
        self.run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")

        self.csv_writer: Any = None
        self.binary_writer: Dpo4LogWriter | None = None
        self.segment_index = -1
        self.segment_started_utc = datetime.now(timezone.utc)
        self.segment_records = 0
        self.records_written = 0
        self.bytes_written = 0
        self.rotation_count = 0
        self.last_rotation_reason = ""
        self._all_paths: list[Path] = []
        self._completed_segments: list[tuple[Path, ...]] = []
        self._failed_segments: list[tuple[Path, ...]] = []
        self._closed_bytes = 0
        self._segment_tainted = False
        self._segment_errors: list[str] = []
        self._closed = False
        self._open_segment()

    def _open_segment(self) -> None:
        self.segment_index += 1
        self.segment_started_utc = datetime.now(timezone.utc)
        self.segment_records = 0
        self._segment_tainted = False
        self._segment_errors = []
        stem = f"logger_{self.run_stamp}_{self.segment_index:04d}"
        self.csv_writer = None
        self.binary_writer = None

        if self.output_format in {LoggerOutputFormat.CSV, LoggerOutputFormat.BOTH}:
            csv_path = self.root / f"{stem}.csv"
            if self.mode is LoggerMode.MEASUREMENTS:
                self.csv_writer = MeasurementCsvStreamWriter(
                    csv_path,
                    self.measurement_slots,
                    sync_policy=self.csv_sync_policy,
                )
            elif self.mode is LoggerMode.BUS:
                self.csv_writer = BusCsvStreamWriter(
                    csv_path,
                    sync_policy=self.csv_sync_policy,
                )
            elif self.mode is LoggerMode.MIXED:
                self.csv_writer = MixedCsvStreamWriter(
                    csv_path,
                    sync_policy=self.csv_sync_policy,
                )
            else:
                self.csv_writer = WaveformCsvStreamWriter(
                    csv_path,
                    sync_policy=self.csv_sync_policy,
                )

        if self.output_format in {LoggerOutputFormat.BINARY, LoggerOutputFormat.BOTH}:
            metadata = dict(self.run_metadata)
            metadata.update(
                {
                    "segment_index": self.segment_index,
                    "run_stamp": self.run_stamp,
                }
            )
            self.binary_writer = Dpo4LogWriter(
                self.root / f"{stem}.dpo4log",
                run_metadata=metadata,
            )

        self._all_paths.extend(path for path in self.current_paths if path not in self._all_paths)
        self._refresh_bytes_written()

    @property
    def current_paths(self) -> tuple[Path, ...]:
        result: list[Path] = []
        if self.csv_writer is not None:
            result.append(self.csv_writer.path)
        if self.binary_writer is not None:
            result.append(self.binary_writer.path)
        return tuple(result)

    @property
    def paths(self) -> tuple[Path, ...]:
        return tuple(self._all_paths)

    @property
    def completed_segments(self) -> tuple[tuple[Path, ...], ...]:
        return tuple(self._completed_segments)

    @property
    def failed_segments(self) -> tuple[tuple[Path, ...], ...]:
        return tuple(self._failed_segments)

    @property
    def current_segment_bytes(self) -> int:
        return sum(path.stat().st_size for path in self.current_paths if path.exists())

    def _estimated_next_bytes(self, record: LoggerRecord) -> int:
        multiplier = 2 if self.output_format is LoggerOutputFormat.BOTH else 1
        return max(1024, int(record.estimated_bytes) * multiplier)

    def _rotation_reason_before(self, record: LoggerRecord) -> str | None:
        if not self.rotation_policy.enabled:
            return None
        return self.rotation_policy.should_rotate(
            segment_bytes=self.current_segment_bytes,
            estimated_next_bytes=self._estimated_next_bytes(record),
            segment_records=self.segment_records,
            segment_started_utc=self.segment_started_utc,
        )

    def _close_current_segment(self) -> tuple[Path, ...]:
        paths = self.current_paths
        errors: list[BaseException] = []
        for writer in (self.csv_writer, self.binary_writer):
            if writer is None:
                continue
            try:
                writer.close()
            except BaseException as exc:  # noqa: BLE001 - aggregate close failures.
                errors.append(exc)
        segment_bytes = sum(path.stat().st_size for path in paths if path.exists())
        self._closed_bytes += segment_bytes
        self.csv_writer = None
        self.binary_writer = None
        if paths:
            if errors or self._segment_tainted:
                self._failed_segments.append(paths)
            else:
                self._completed_segments.append(paths)
        self._refresh_bytes_written()
        if errors:
            messages = [*self._segment_errors, *(str(error) for error in errors)]
            raise RuntimeError("; ".join(message for message in messages if message))
        return paths

    def rotate(self, reason: str) -> None:
        if self._closed:
            raise RuntimeError("Logger output session is closed.")
        if self.segment_records <= 0:
            return
        self._close_current_segment()
        self.rotation_count += 1
        self.last_rotation_reason = str(reason)
        self._open_segment()

    def append(self, record: LoggerRecord) -> None:
        if self._closed:
            raise RuntimeError("Logger output session is closed.")
        reason = self._rotation_reason_before(record)
        if reason:
            self.rotate(reason)

        try:
            if self.csv_writer is not None:
                self.csv_writer.append(record)
            if self.binary_writer is not None:
                self.binary_writer.append(record)
        except BaseException as exc:  # noqa: BLE001 - mark partially written segment unsafe.
            self._segment_tainted = True
            self._segment_errors.append(str(exc))
            self._refresh_bytes_written()
            raise
        self.segment_records += 1
        self.records_written += 1
        self._refresh_bytes_written()

    def _refresh_bytes_written(self) -> None:
        self.bytes_written = self._closed_bytes + self.current_segment_bytes

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._close_current_segment()
        finally:
            self._closed = True
            self._refresh_bytes_written()


__all__ = ["LoggerOutputSession"]
