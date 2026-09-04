"""Crash-tolerant append-only DPO4LOG binary Logger container.

Inspection and conversion APIs are streaming by default: they retain at most one
record payload (conversion) or one fixed-size checksum chunk (inspection), never
the complete multi-hour log in memory.
"""

from __future__ import annotations

import json
import os
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Iterator, Mapping

from .models import LoggerRecord, WaveformSnapshot

MAGIC = b"DPO4LOG\x00"
SCHEMA_VERSION = 1
_FRAME_MARKER = b"FRM1"
_FRAME_RECORD = 1
_FRAME_END = 255
_FILE_PREFIX = struct.Struct(">8sHI")
_FRAME_PREFIX = struct.Struct(">4sB3xIII")
MAX_HEADER_BYTES = 16 * 1024 * 1024
MAX_FRAME_METADATA_BYTES = 16 * 1024 * 1024
MAX_FRAME_PAYLOAD_BYTES = 1024 * 1024 * 1024
_SCAN_CHUNK_BYTES = 1024 * 1024


class Dpo4LogError(ValueError):
    """Base error for invalid/corrupt DPO4LOG content."""


class Dpo4LogCorruptionError(Dpo4LogError):
    """Raised by strict streaming iteration on a damaged/incomplete frame."""


@dataclass(frozen=True)
class Dpo4LogScanResult:
    header: Mapping[str, Any]
    records: tuple[LoggerRecord, ...] = ()
    truncated: bool = False
    error: str = ""
    record_count: int = 0
    clean_end: bool = False

    @property
    def loaded_records(self) -> bool:
        """Return whether this scan explicitly materialized decoded records."""
        return bool(self.records) or (self.record_count == 0 and self.clean_end)


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _waveform_metadata(snapshot: WaveformSnapshot, *, offset: int, length: int) -> dict[str, Any]:
    return {
        "source": snapshot.source,
        "label": snapshot.label,
        "start_index": snapshot.start_index,
        "stop_index": snapshot.stop_index,
        "acquired_utc": snapshot.acquired_utc,
        "typecode": snapshot.typecode,
        "sample_count": snapshot.sample_count,
        "byte_order": snapshot.byte_order,
        "preamble": dict(snapshot.preamble),
        "payload_offset": offset,
        "payload_length": length,
    }


def encode_record(record: LoggerRecord) -> tuple[bytes, bytes]:
    payload = bytearray()
    waveforms: list[dict[str, Any]] = []
    for snapshot in record.waveforms:
        offset = len(payload)
        sample_bytes = bytes(snapshot.sample_bytes)
        payload.extend(sample_bytes)
        waveforms.append(_waveform_metadata(snapshot, offset=offset, length=len(sample_bytes)))
    metadata = {
        "sequence": int(record.sequence),
        "captured_utc": str(record.captured_utc),
        "captured_monotonic": float(record.captured_monotonic),
        "waveforms": waveforms,
        "measurements": {str(key): value for key, value in record.measurements.items()},
        "measurement_errors": {str(key): str(value) for key, value in record.measurement_errors.items()},
        "bus_events": {str(key): list(value) for key, value in record.bus_events.items()},
        "metadata": dict(record.metadata),
    }
    return _json_bytes(metadata), bytes(payload)


def decode_record(metadata_bytes: bytes, payload: bytes) -> LoggerRecord:
    metadata = json.loads(metadata_bytes.decode("utf-8"))
    if not isinstance(metadata, dict):
        raise Dpo4LogError("DPO4LOG record metadata must be an object.")
    waveforms: list[WaveformSnapshot] = []
    for item in metadata.get("waveforms", []):
        if not isinstance(item, dict):
            raise Dpo4LogError("DPO4LOG waveform metadata must be an object.")
        offset = int(item["payload_offset"])
        length = int(item["payload_length"])
        if offset < 0 or length < 0 or offset + length > len(payload):
            raise Dpo4LogError("DPO4LOG waveform payload range is invalid.")
        waveforms.append(
            WaveformSnapshot(
                source=str(item["source"]),
                label=str(item.get("label", item["source"])),
                start_index=int(item["start_index"]),
                stop_index=int(item["stop_index"]),
                acquired_utc=str(item["acquired_utc"]),
                typecode=str(item["typecode"]),
                sample_bytes=bytes(payload[offset : offset + length]),
                sample_count=int(item["sample_count"]),
                byte_order=str(item["byte_order"]),
                preamble=dict(item["preamble"]),
            )
        )
    return LoggerRecord(
        sequence=int(metadata["sequence"]),
        captured_utc=str(metadata["captured_utc"]),
        captured_monotonic=float(metadata.get("captured_monotonic", 0.0)),
        waveforms=tuple(waveforms),
        measurements={int(key): value for key, value in dict(metadata.get("measurements", {})).items()},
        measurement_errors={int(key): str(value) for key, value in dict(metadata.get("measurement_errors", {})).items()},
        bus_events={
            int(key): tuple(dict(event) for event in events)
            for key, events in dict(metadata.get("bus_events", {})).items()
        },
        metadata=dict(metadata.get("metadata", {})),
    )


class Dpo4LogWriter:
    """Write independently checksummed complete frames; fsync policy is configurable."""

    def __init__(
        self,
        path: str | Path,
        *,
        run_metadata: Mapping[str, Any] | None = None,
        fsync_each_record: bool = False,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("xb")
        self._closed = False
        self.fsync_each_record = bool(fsync_each_record)
        header = _json_bytes(dict(run_metadata or {}))
        if len(header) > MAX_HEADER_BYTES:
            self._handle.close()
            self._closed = True
            raise ValueError("DPO4LOG run metadata exceeds the maximum header size.")
        self._handle.write(_FILE_PREFIX.pack(MAGIC, SCHEMA_VERSION, len(header)))
        self._handle.write(header)
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self.records_written = 0
        self.bytes_written = self.path.stat().st_size

    def _write_frame(self, frame_type: int, metadata: bytes, payload: bytes) -> None:
        if len(metadata) > MAX_FRAME_METADATA_BYTES:
            raise ValueError("DPO4LOG frame metadata exceeds safety limit.")
        if len(payload) > MAX_FRAME_PAYLOAD_BYTES:
            raise ValueError("DPO4LOG frame payload exceeds safety limit.")
        checksum = zlib.crc32(metadata)
        checksum = zlib.crc32(payload, checksum) & 0xFFFFFFFF
        self._handle.write(
            _FRAME_PREFIX.pack(_FRAME_MARKER, int(frame_type), len(metadata), len(payload), checksum)
        )
        self._handle.write(metadata)
        self._handle.write(payload)
        self._handle.flush()
        if self.fsync_each_record:
            os.fsync(self._handle.fileno())
        self.bytes_written = self.path.stat().st_size

    def append(self, record: LoggerRecord) -> None:
        if self._closed:
            raise RuntimeError("DPO4LOG writer is closed.")
        metadata, payload = encode_record(record)
        self._write_frame(_FRAME_RECORD, metadata, payload)
        self.records_written += 1

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._write_frame(_FRAME_END, _json_bytes({"records": self.records_written}), b"")
            os.fsync(self._handle.fileno())
        finally:
            self._handle.close()
            self._closed = True

    def __enter__(self) -> "Dpo4LogWriter":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def _read_exact(handle: BinaryIO, size: int) -> bytes | None:
    data = handle.read(size)
    if not data:
        return None
    if len(data) != size:
        raise EOFError(f"Expected {size} bytes, got {len(data)}.")
    return data


def _read_header(handle: BinaryIO) -> dict[str, Any]:
    prefix = _read_exact(handle, _FILE_PREFIX.size)
    if prefix is None:
        raise Dpo4LogError("Empty DPO4LOG file.")
    magic, version, header_length = _FILE_PREFIX.unpack(prefix)
    if magic != MAGIC:
        raise Dpo4LogError("Not a DPO4LOG file.")
    if version != SCHEMA_VERSION:
        raise Dpo4LogError(f"Unsupported DPO4LOG schema version: {version}.")
    if header_length > MAX_HEADER_BYTES:
        raise Dpo4LogCorruptionError(
            f"DPO4LOG header length {header_length} exceeds safety limit {MAX_HEADER_BYTES}."
        )
    header_bytes = _read_exact(handle, header_length)
    if header_bytes is None:
        raise Dpo4LogCorruptionError("DPO4LOG header is truncated.")
    try:
        header = json.loads(header_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Dpo4LogCorruptionError(f"Invalid DPO4LOG header JSON: {exc}") from exc
    return dict(header) if isinstance(header, dict) else {"value": header}


def _validate_frame_lengths(metadata_length: int, payload_length: int, *, offset: int) -> None:
    if metadata_length > MAX_FRAME_METADATA_BYTES:
        raise Dpo4LogCorruptionError(
            f"Frame metadata length {metadata_length} exceeds safety limit at offset {offset}."
        )
    if payload_length > MAX_FRAME_PAYLOAD_BYTES:
        raise Dpo4LogCorruptionError(
            f"Frame payload length {payload_length} exceeds safety limit at offset {offset}."
        )


def _stream_payload_crc(handle: BinaryIO, payload_length: int, checksum: int) -> int:
    remaining = payload_length
    actual = checksum
    while remaining:
        chunk = handle.read(min(_SCAN_CHUNK_BYTES, remaining))
        if not chunk:
            raise EOFError(f"Expected {remaining} additional payload bytes.")
        actual = zlib.crc32(chunk, actual)
        remaining -= len(chunk)
    return actual & 0xFFFFFFFF


def scan_dpo4log(path: str | Path, *, load_records: bool = False) -> Dpo4LogScanResult:
    """Inspect a DPO4LOG file using bounded memory.

    By default record payloads are streamed only through CRC calculation and are
    not retained. ``load_records=True`` is an explicit compatibility/debug option
    that may use memory proportional to the whole file; production inspection and
    conversion should use ``iter_dpo4log_records`` instead.
    """

    target = Path(path)
    records: list[LoggerRecord] = []
    record_count = 0
    clean_end = False
    truncated = False
    error = ""
    with target.open("rb") as handle:
        header = _read_header(handle)
        while True:
            position = handle.tell()
            raw_prefix = handle.read(_FRAME_PREFIX.size)
            if not raw_prefix:
                break
            if len(raw_prefix) != _FRAME_PREFIX.size:
                truncated = True
                error = f"Truncated frame prefix at offset {position}."
                break
            marker, frame_type, metadata_length, payload_length, checksum = _FRAME_PREFIX.unpack(raw_prefix)
            if marker != _FRAME_MARKER:
                truncated = True
                error = f"Invalid frame marker at offset {position}."
                break
            try:
                _validate_frame_lengths(metadata_length, payload_length, offset=position)
                metadata = _read_exact(handle, metadata_length)
                if metadata is None and metadata_length:
                    raise EOFError("Frame metadata is truncated.")
                metadata = metadata or b""
                actual = zlib.crc32(metadata)
                if load_records:
                    payload = _read_exact(handle, payload_length)
                    if payload is None and payload_length:
                        raise EOFError("Frame payload is truncated.")
                    payload = payload or b""
                    actual = zlib.crc32(payload, actual) & 0xFFFFFFFF
                else:
                    payload = b""
                    actual = _stream_payload_crc(handle, payload_length, actual)
            except (EOFError, Dpo4LogCorruptionError) as exc:
                truncated = True
                error = f"{exc}"
                break
            if actual != checksum:
                truncated = True
                error = f"CRC mismatch at frame offset {position}."
                break
            if frame_type == _FRAME_RECORD:
                record_count += 1
                if load_records:
                    try:
                        records.append(decode_record(metadata, payload))
                    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                        truncated = True
                        error = f"Invalid record at frame offset {position}: {exc}"
                        break
            elif frame_type == _FRAME_END:
                clean_end = True
                try:
                    end_metadata = json.loads(metadata.decode("utf-8")) if metadata else {}
                    expected = int(end_metadata.get("records", record_count))
                    if expected != record_count:
                        truncated = True
                        error = (
                            f"END frame reports {expected} records but {record_count} complete "
                            "record frames were found."
                        )
                except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                    truncated = True
                    error = f"Invalid END frame metadata: {exc}"
                if handle.read(1):
                    truncated = True
                    error = error or "Trailing bytes found after END frame."
                break
            else:
                continue

    return Dpo4LogScanResult(
        header=header,
        records=tuple(records),
        truncated=truncated,
        error=error,
        record_count=record_count,
        clean_end=clean_end,
    )


def iter_dpo4log_records(
    path: str | Path,
    *,
    strict: bool = True,
) -> Iterator[LoggerRecord]:
    """Yield complete records one at a time, never retaining prior payloads."""

    with Path(path).open("rb") as handle:
        _read_header(handle)
        while True:
            position = handle.tell()
            raw_prefix = handle.read(_FRAME_PREFIX.size)
            if not raw_prefix:
                if strict:
                    raise Dpo4LogCorruptionError("DPO4LOG ended without a clean END frame.")
                return
            if len(raw_prefix) != _FRAME_PREFIX.size:
                if strict:
                    raise Dpo4LogCorruptionError(f"Truncated frame prefix at offset {position}.")
                return
            marker, frame_type, metadata_length, payload_length, checksum = _FRAME_PREFIX.unpack(raw_prefix)
            try:
                if marker != _FRAME_MARKER:
                    raise Dpo4LogCorruptionError(f"Invalid frame marker at offset {position}.")
                _validate_frame_lengths(metadata_length, payload_length, offset=position)
                metadata = _read_exact(handle, metadata_length)
                if metadata is None and metadata_length:
                    raise EOFError("Frame metadata is truncated.")
                payload = _read_exact(handle, payload_length)
                if payload is None and payload_length:
                    raise EOFError("Frame payload is truncated.")
                metadata = metadata or b""
                payload = payload or b""
                actual = zlib.crc32(metadata)
                actual = zlib.crc32(payload, actual) & 0xFFFFFFFF
                if actual != checksum:
                    raise Dpo4LogCorruptionError(f"CRC mismatch at frame offset {position}.")
            except (EOFError, Dpo4LogCorruptionError) as exc:
                if strict:
                    if isinstance(exc, Dpo4LogCorruptionError):
                        raise
                    raise Dpo4LogCorruptionError(str(exc)) from exc
                return
            if frame_type == _FRAME_END:
                if strict and handle.read(1):
                    raise Dpo4LogCorruptionError("Trailing bytes found after END frame.")
                return
            if frame_type != _FRAME_RECORD:
                continue
            try:
                yield decode_record(metadata, payload)
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                if strict:
                    raise Dpo4LogCorruptionError(
                        f"Invalid record at frame offset {position}: {exc}"
                    ) from exc
                return


__all__ = [
    "Dpo4LogCorruptionError",
    "Dpo4LogError",
    "Dpo4LogScanResult",
    "Dpo4LogWriter",
    "MAGIC",
    "MAX_FRAME_METADATA_BYTES",
    "MAX_FRAME_PAYLOAD_BYTES",
    "MAX_HEADER_BYTES",
    "SCHEMA_VERSION",
    "decode_record",
    "encode_record",
    "iter_dpo4log_records",
    "scan_dpo4log",
]
