"""Crash-tolerant append-only DPO4LOG binary Logger container."""

from __future__ import annotations

import json
import os
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Mapping

from .models import LoggerRecord, WaveformSnapshot

MAGIC = b"DPO4LOG\x00"
SCHEMA_VERSION = 1
_FRAME_MARKER = b"FRM1"
_FRAME_RECORD = 1
_FRAME_END = 255
_FILE_PREFIX = struct.Struct(">8sHI")
_FRAME_PREFIX = struct.Struct(">4sB3xIII")


@dataclass(frozen=True)
class Dpo4LogScanResult:
    header: Mapping[str, Any]
    records: tuple[LoggerRecord, ...]
    truncated: bool = False
    error: str = ""


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
        raise ValueError("DPO4LOG record metadata must be an object.")
    waveforms: list[WaveformSnapshot] = []
    for item in metadata.get("waveforms", []):
        if not isinstance(item, dict):
            raise ValueError("DPO4LOG waveform metadata must be an object.")
        offset = int(item["payload_offset"])
        length = int(item["payload_length"])
        if offset < 0 or length < 0 or offset + length > len(payload):
            raise ValueError("DPO4LOG waveform payload range is invalid.")
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
        self._handle.write(_FILE_PREFIX.pack(MAGIC, SCHEMA_VERSION, len(header)))
        self._handle.write(header)
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self.records_written = 0
        self.bytes_written = self.path.stat().st_size

    def _write_frame(self, frame_type: int, metadata: bytes, payload: bytes) -> None:
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


def scan_dpo4log(path: str | Path) -> Dpo4LogScanResult:
    target = Path(path)
    records: list[LoggerRecord] = []
    truncated = False
    error = ""
    with target.open("rb") as handle:
        prefix = _read_exact(handle, _FILE_PREFIX.size)
        if prefix is None:
            raise ValueError("Empty DPO4LOG file.")
        magic, version, header_length = _FILE_PREFIX.unpack(prefix)
        if magic != MAGIC:
            raise ValueError("Not a DPO4LOG file.")
        if version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported DPO4LOG schema version: {version}.")
        header_bytes = _read_exact(handle, header_length)
        if header_bytes is None:
            raise ValueError("DPO4LOG header is truncated.")
        header = json.loads(header_bytes.decode("utf-8"))
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
            metadata = handle.read(metadata_length)
            payload = handle.read(payload_length)
            if len(metadata) != metadata_length or len(payload) != payload_length:
                truncated = True
                error = f"Truncated frame at offset {position}."
                break
            actual = zlib.crc32(metadata)
            actual = zlib.crc32(payload, actual) & 0xFFFFFFFF
            if actual != checksum:
                truncated = True
                error = f"CRC mismatch at frame offset {position}."
                break
            if frame_type == _FRAME_RECORD:
                records.append(decode_record(metadata, payload))
            elif frame_type == _FRAME_END:
                break
            else:
                # Schema-compatible unknown frame types are skipped after CRC validation.
                continue
    return Dpo4LogScanResult(
        header=dict(header) if isinstance(header, dict) else {"value": header},
        records=tuple(records),
        truncated=truncated,
        error=error,
    )


__all__ = [
    "Dpo4LogScanResult",
    "Dpo4LogWriter",
    "MAGIC",
    "SCHEMA_VERSION",
    "decode_record",
    "encode_record",
    "scan_dpo4log",
]
