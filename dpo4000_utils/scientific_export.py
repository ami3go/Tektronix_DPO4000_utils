"""A21 scientific waveform export with deterministic round-trip import.

Two formats are supported:

* ``.npz`` — NumPy-native arrays for scientific Python workflows.  Each trace
  contains raw samples plus derived X/Y float64 arrays and a JSON manifest.
* ``.dpoz`` — a portable ZIP archive containing a JSON manifest, exact raw
  samples, and one human-readable CSV per trace.  It requires no third-party
  library to read/write through this module.

The exporter performs no instrument I/O.  Callers acquire :class:`WaveformData`
through the public driver API, then hand those values to this module.  Output is
written to a same-directory temporary file and atomically replaced on success.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import sys
import time
import zipfile
from array import array
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from .waveform import WaveformData, WaveformPreamble

SCIENTIFIC_SCHEMA_VERSION = 1
_MANIFEST_NAME = "manifest.json"
_NPZ_MANIFEST_KEY = "__manifest_utf8__"
_SUPPORTED_RAW_TYPECODES = frozenset({"b", "B", "h", "H", "d"})


class ScientificExportError(ValueError):
    """Raised when an A21 dataset or archive is invalid/unavailable."""


class ScientificFormat(str, Enum):
    NPZ = "npz"
    DPOZ = "dpoz"


def normalize_scientific_format(value: ScientificFormat | str) -> ScientificFormat:
    if isinstance(value, ScientificFormat):
        return value
    token = str(value or "").strip().lower().replace(".", "")
    aliases = {
        "numpy": ScientificFormat.NPZ,
        "numpy_npz": ScientificFormat.NPZ,
        "portable": ScientificFormat.DPOZ,
        "zip": ScientificFormat.DPOZ,
        "dpozip": ScientificFormat.DPOZ,
    }
    if token in aliases:
        return aliases[token]
    try:
        return ScientificFormat(token)
    except ValueError as exc:
        raise ScientificExportError(
            f"Unsupported scientific export format {value!r}; expected 'npz' or 'dpoz'."
        ) from exc


def infer_scientific_format(path: str | Path) -> ScientificFormat:
    suffix = Path(path).suffix.lower()
    if suffix == ".npz":
        return ScientificFormat.NPZ
    if suffix in {".dpoz", ".zip"}:
        return ScientificFormat.DPOZ
    raise ScientificExportError(
        f"Cannot infer scientific format from {Path(path).name!r}; use .npz or .dpoz."
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalized_datetime(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ScientificExportError(f"{field_name} must be a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _json_value(value: Any, *, field_name: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ScientificExportError(f"{field_name} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ScientificExportError(f"{field_name} mapping keys must be strings")
            output[key] = _json_value(item, field_name=f"{field_name}.{key}")
        return output
    if isinstance(value, (list, tuple)):
        return [
            _json_value(item, field_name=f"{field_name}[{index}]")
            for index, item in enumerate(value)
        ]
    raise ScientificExportError(
        f"{field_name} contains unsupported value type {type(value).__name__}"
    )


def _validate_preamble(preamble: WaveformPreamble) -> None:
    if not isinstance(preamble, WaveformPreamble):
        raise ScientificExportError("waveform preamble must be WaveformPreamble")
    finite_fields = (
        "x_increment",
        "x_zero",
        "point_offset",
        "y_multiplier",
        "y_offset",
        "y_zero",
    )
    for name in finite_fields:
        value = float(getattr(preamble, name))
        if not math.isfinite(value):
            raise ScientificExportError(f"preamble {name} must be finite")
    if preamble.x_increment <= 0:
        raise ScientificExportError("preamble x_increment must be > 0")
    if preamble.record_point_count <= 0:
        raise ScientificExportError("preamble record_point_count must be > 0")


def _validate_waveform(waveform: WaveformData) -> None:
    if not isinstance(waveform, WaveformData):
        raise ScientificExportError("scientific export values must be WaveformData")
    if not isinstance(waveform.source, str) or not waveform.source.strip():
        raise ScientificExportError("waveform source must be non-empty")
    if waveform.start_index <= 0 or waveform.stop_index < waveform.start_index:
        raise ScientificExportError(
            f"{waveform.source} has invalid transfer range "
            f"{waveform.start_index}..{waveform.stop_index}"
        )
    expected = waveform.stop_index - waveform.start_index + 1
    if waveform.sample_count != expected:
        raise ScientificExportError(
            f"{waveform.source} sample count {waveform.sample_count} does not match "
            f"transfer range size {expected}"
        )
    if waveform.sample_count != waveform.preamble.record_point_count:
        raise ScientificExportError(
            f"{waveform.source} sample count {waveform.sample_count} does not match "
            f"preamble record_point_count {waveform.preamble.record_point_count}"
        )
    if waveform.samples.typecode not in _SUPPORTED_RAW_TYPECODES:
        raise ScientificExportError(
            f"{waveform.source} raw typecode {waveform.samples.typecode!r} is unsupported"
        )
    _validate_preamble(waveform.preamble)
    _normalized_datetime(waveform.acquired_at, field_name=f"{waveform.source}.acquired_at")


@dataclass(frozen=True)
class ScientificDataset:
    waveforms: tuple[WaveformData, ...]
    metadata: Mapping[str, Any]
    created_at: datetime
    schema_version: int = SCIENTIFIC_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCIENTIFIC_SCHEMA_VERSION or isinstance(
            self.schema_version, bool
        ):
            raise ScientificExportError(
                f"Unsupported scientific schema version: {self.schema_version!r}"
            )
        if not isinstance(self.waveforms, tuple):
            object.__setattr__(self, "waveforms", tuple(self.waveforms))
        if not self.waveforms:
            raise ScientificExportError("scientific dataset must contain at least one trace")
        sources: set[str] = set()
        for waveform in self.waveforms:
            _validate_waveform(waveform)
            if waveform.source in sources:
                raise ScientificExportError(
                    f"scientific dataset contains duplicate source {waveform.source!r}"
                )
            sources.add(waveform.source)
        object.__setattr__(
            self,
            "metadata",
            _json_value(self.metadata, field_name="metadata"),
        )
        object.__setattr__(
            self,
            "created_at",
            _normalized_datetime(self.created_at, field_name="created_at"),
        )

    @property
    def trace_count(self) -> int:
        return len(self.waveforms)

    @property
    def sample_count(self) -> int:
        return sum(waveform.sample_count for waveform in self.waveforms)

    def by_source(self) -> dict[str, WaveformData]:
        return {waveform.source: waveform for waveform in self.waveforms}


@dataclass(frozen=True)
class ScientificExportResult:
    path: Path
    format: ScientificFormat
    trace_count: int
    sample_count: int
    bytes_written: int
    duration_s: float

    @property
    def samples_per_second(self) -> float:
        return self.sample_count / self.duration_s if self.duration_s > 0 else math.inf

    @property
    def megabytes_per_second(self) -> float:
        megabytes = self.bytes_written / 1_000_000.0
        return megabytes / self.duration_s if self.duration_s > 0 else math.inf


@dataclass(frozen=True)
class ScientificImportResult:
    dataset: ScientificDataset
    path: Path
    format: ScientificFormat
    bytes_read: int
    duration_s: float

    @property
    def samples_per_second(self) -> float:
        count = self.dataset.sample_count
        return count / self.duration_s if self.duration_s > 0 else math.inf


def scientific_dataset_from_waveforms(
    waveforms: Mapping[str, WaveformData] | Sequence[WaveformData],
    *,
    metadata: Mapping[str, Any] | None = None,
    created_at: datetime | None = None,
) -> ScientificDataset:
    if isinstance(waveforms, Mapping):
        values = tuple(waveforms.values())
    elif isinstance(waveforms, Sequence) and not isinstance(waveforms, (str, bytes)):
        values = tuple(waveforms)
    else:
        raise ScientificExportError("waveforms must be a mapping or sequence")
    return ScientificDataset(
        waveforms=values,
        metadata={} if metadata is None else metadata,
        created_at=created_at or _utc_now(),
    )


def _trace_manifest(index: int, waveform: WaveformData) -> dict[str, Any]:
    return {
        "index": index,
        "source": waveform.source,
        "label": waveform.label,
        "start_index": waveform.start_index,
        "stop_index": waveform.stop_index,
        "requested_encoding": waveform.requested_encoding,
        "acquired_at": _normalized_datetime(
            waveform.acquired_at,
            field_name=f"{waveform.source}.acquired_at",
        ).isoformat(),
        "sample_count": waveform.sample_count,
        "raw_typecode": waveform.samples.typecode,
        "preamble": asdict(waveform.preamble),
    }


def _build_manifest(dataset: ScientificDataset, export_format: ScientificFormat) -> dict[str, Any]:
    return {
        "schema": "dpo4000-scientific",
        "schema_version": dataset.schema_version,
        "format": export_format.value,
        "created_at": dataset.created_at.isoformat(),
        "metadata": dict(dataset.metadata),
        "traces": [
            _trace_manifest(index, waveform)
            for index, waveform in enumerate(dataset.waveforms)
        ],
    }


def _atomic_temp_path(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    handle = NamedTemporaryFile(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
        delete=False,
    )
    path = Path(handle.name)
    handle.close()
    return path


def _atomic_replace(temp_path: Path, output: Path) -> None:
    os.replace(temp_path, output)


def _portable_raw_bytes(samples: array) -> bytes:
    values = array(samples.typecode, samples)
    if sys.byteorder != "little" and values.itemsize > 1:
        values.byteswap()
    return values.tobytes()


def _restore_portable_raw(raw: bytes, typecode: str, expected_count: int) -> array:
    if typecode not in _SUPPORTED_RAW_TYPECODES:
        raise ScientificExportError(f"Archive raw typecode {typecode!r} is unsupported")
    values = array(typecode)
    try:
        values.frombytes(raw)
    except (ValueError, EOFError) as exc:
        raise ScientificExportError("Malformed raw waveform payload") from exc
    if sys.byteorder != "little" and values.itemsize > 1:
        values.byteswap()
    if len(values) != expected_count:
        raise ScientificExportError(
            f"Raw waveform contains {len(values)} samples, expected {expected_count}"
        )
    return values


def _safe_trace_stem(index: int, source: str) -> str:
    safe = "".join(character if character.isalnum() else "_" for character in source)
    return f"{index:03d}_{safe or 'trace'}"


def _write_dpoz(
    temp_path: Path,
    dataset: ScientificDataset,
    *,
    compressed: bool,
) -> None:
    compression = zipfile.ZIP_DEFLATED if compressed else zipfile.ZIP_STORED
    manifest = _build_manifest(dataset, ScientificFormat.DPOZ)
    with zipfile.ZipFile(
        temp_path,
        mode="w",
        compression=compression,
        allowZip64=True,
    ) as archive:
        archive.writestr(
            _MANIFEST_NAME,
            json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n",
        )
        for index, waveform in enumerate(dataset.waveforms):
            stem = _safe_trace_stem(index, waveform.source)
            archive.writestr(
                f"traces/{stem}.raw",
                _portable_raw_bytes(waveform.samples),
            )
            with archive.open(f"traces/{stem}.csv", mode="w", force_zip64=True) as binary:
                text = io.TextIOWrapper(binary, encoding="utf-8", newline="")
                writer = csv.writer(text)
                writer.writerow(
                    [
                        "index",
                        f"x ({waveform.preamble.x_unit or 's'})",
                        f"y ({waveform.preamble.y_unit or 'V'})",
                    ]
                )
                for point in range(waveform.sample_count):
                    writer.writerow(
                        [
                            point,
                            waveform.time_at(point),
                            waveform.voltage_at(point),
                        ]
                    )
                text.flush()
                text.detach()


def _require_numpy():
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised without scientific extra
        raise ScientificExportError(
            "NumPy is required for .npz scientific export/import. "
            "Install dpo4000-utils[scientific] or the DPO4000 Desk extra."
        ) from exc
    return np


def _write_npz(
    temp_path: Path,
    dataset: ScientificDataset,
    *,
    compressed: bool,
) -> None:
    np = _require_numpy()
    manifest = _build_manifest(dataset, ScientificFormat.NPZ)
    payload: dict[str, Any] = {
        _NPZ_MANIFEST_KEY: np.frombuffer(
            json.dumps(manifest, sort_keys=True).encode("utf-8"),
            dtype=np.uint8,
        )
    }
    for index, waveform in enumerate(dataset.waveforms):
        prefix = f"trace_{index:03d}"
        raw = np.asarray(waveform.samples)
        indices = np.arange(waveform.sample_count, dtype=np.float64)
        time_axis = waveform.preamble.x_zero + waveform.preamble.x_increment * (
            indices - waveform.preamble.point_offset
        )
        values = (
            raw.astype(np.float64, copy=False) - waveform.preamble.y_offset
        ) * waveform.preamble.y_multiplier + waveform.preamble.y_zero
        payload[f"{prefix}_raw"] = raw
        payload[f"{prefix}_x"] = time_axis
        payload[f"{prefix}_y"] = values
    writer = np.savez_compressed if compressed else np.savez
    with temp_path.open("wb") as handle:
        writer(handle, **payload)


def export_scientific_dataset(
    path: str | Path,
    dataset: ScientificDataset | Mapping[str, WaveformData] | Sequence[WaveformData],
    *,
    format: ScientificFormat | str | None = None,
    metadata: Mapping[str, Any] | None = None,
    compressed: bool = False,
) -> ScientificExportResult:
    """Write an A21 dataset atomically and return throughput metrics."""
    output = Path(path)
    export_format = infer_scientific_format(output) if format is None else normalize_scientific_format(format)
    if isinstance(dataset, ScientificDataset):
        if metadata is not None:
            raise ScientificExportError(
                "metadata must be supplied when building a dataset, not when exporting one"
            )
        normalized = dataset
    else:
        normalized = scientific_dataset_from_waveforms(dataset, metadata=metadata)

    temp_path = _atomic_temp_path(output)
    started = time.perf_counter()
    try:
        if export_format is ScientificFormat.NPZ:
            _write_npz(temp_path, normalized, compressed=compressed)
        else:
            _write_dpoz(temp_path, normalized, compressed=compressed)
        _atomic_replace(temp_path, output)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    duration = max(0.0, time.perf_counter() - started)
    return ScientificExportResult(
        path=output,
        format=export_format,
        trace_count=normalized.trace_count,
        sample_count=normalized.sample_count,
        bytes_written=output.stat().st_size,
        duration_s=duration,
    )


def _parse_manifest(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScientificExportError("Scientific archive manifest is not valid UTF-8 JSON") from exc
    if not isinstance(value, Mapping):
        raise ScientificExportError("Scientific archive manifest must be a JSON object")
    if value.get("schema") != "dpo4000-scientific":
        raise ScientificExportError("Scientific archive has an unsupported schema identifier")
    if value.get("schema_version") != SCIENTIFIC_SCHEMA_VERSION:
        raise ScientificExportError(
            f"Unsupported scientific schema version: {value.get('schema_version')!r}"
        )
    traces = value.get("traces")
    if not isinstance(traces, list) or not traces:
        raise ScientificExportError("Scientific archive must contain a non-empty traces list")
    return dict(value)


def _waveform_from_manifest(trace: Mapping[str, Any], samples: array) -> WaveformData:
    required = {
        "source",
        "label",
        "start_index",
        "stop_index",
        "requested_encoding",
        "acquired_at",
        "sample_count",
        "raw_typecode",
        "preamble",
    }
    missing = required - set(trace)
    if missing:
        raise ScientificExportError(
            f"Scientific trace manifest is missing fields: {sorted(missing)!r}"
        )
    if len(samples) != trace["sample_count"]:
        raise ScientificExportError(
            f"Scientific trace {trace.get('source')!r} sample count mismatch"
        )
    preamble_raw = trace["preamble"]
    if not isinstance(preamble_raw, Mapping):
        raise ScientificExportError("Scientific trace preamble must be an object")
    try:
        preamble = WaveformPreamble(**dict(preamble_raw))
        acquired_at = datetime.fromisoformat(str(trace["acquired_at"]))
    except (TypeError, ValueError) as exc:
        raise ScientificExportError("Scientific trace metadata is malformed") from exc
    waveform = WaveformData(
        source=str(trace["source"]),
        label=str(trace["label"]),
        start_index=int(trace["start_index"]),
        stop_index=int(trace["stop_index"]),
        requested_encoding=str(trace["requested_encoding"]),
        preamble=preamble,
        samples=samples,
        acquired_at=acquired_at,
    )
    _validate_waveform(waveform)
    return waveform


def _dataset_from_manifest_and_samples(
    manifest: Mapping[str, Any],
    samples_by_index: Mapping[int, array],
) -> ScientificDataset:
    traces = manifest["traces"]
    waveforms: list[WaveformData] = []
    seen_indices: set[int] = set()
    for raw_trace in traces:
        if not isinstance(raw_trace, Mapping):
            raise ScientificExportError("Scientific trace entry must be an object")
        index = raw_trace.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ScientificExportError("Scientific trace index must be a non-negative integer")
        if index in seen_indices:
            raise ScientificExportError(f"Duplicate scientific trace index {index}")
        seen_indices.add(index)
        samples = samples_by_index.get(index)
        if samples is None:
            raise ScientificExportError(f"Scientific trace {index} raw samples are missing")
        waveforms.append(_waveform_from_manifest(raw_trace, samples))
    try:
        created_at = datetime.fromisoformat(str(manifest["created_at"]))
    except (KeyError, ValueError) as exc:
        raise ScientificExportError("Scientific archive created_at is missing or malformed") from exc
    metadata = manifest.get("metadata", {})
    if not isinstance(metadata, Mapping):
        raise ScientificExportError("Scientific archive metadata must be an object")
    return ScientificDataset(
        waveforms=tuple(waveforms),
        metadata=dict(metadata),
        created_at=created_at,
        schema_version=int(manifest["schema_version"]),
    )


def _read_dpoz(path: Path) -> ScientificDataset:
    try:
        with zipfile.ZipFile(path, mode="r") as archive:
            manifest = _parse_manifest(archive.read(_MANIFEST_NAME))
            samples_by_index: dict[int, array] = {}
            for raw_trace in manifest["traces"]:
                index = raw_trace.get("index")
                source = raw_trace.get("source", "trace")
                stem = _safe_trace_stem(index, str(source))
                expected = raw_trace.get("sample_count")
                typecode = raw_trace.get("raw_typecode")
                if isinstance(expected, bool) or not isinstance(expected, int) or expected <= 0:
                    raise ScientificExportError("Scientific trace sample_count must be positive")
                samples_by_index[index] = _restore_portable_raw(
                    archive.read(f"traces/{stem}.raw"),
                    str(typecode),
                    expected,
                )
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ScientificExportError("Malformed portable scientific archive") from exc
    return _dataset_from_manifest_and_samples(manifest, samples_by_index)


def _read_npz(path: Path) -> ScientificDataset:
    np = _require_numpy()
    try:
        with np.load(path, allow_pickle=False) as archive:
            if _NPZ_MANIFEST_KEY not in archive:
                raise ScientificExportError("NPZ scientific archive has no manifest")
            manifest = _parse_manifest(archive[_NPZ_MANIFEST_KEY].tobytes())
            samples_by_index: dict[int, array] = {}
            for raw_trace in manifest["traces"]:
                index = raw_trace.get("index")
                typecode = str(raw_trace.get("raw_typecode"))
                expected = raw_trace.get("sample_count")
                if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                    raise ScientificExportError("Scientific trace index must be non-negative")
                if isinstance(expected, bool) or not isinstance(expected, int) or expected <= 0:
                    raise ScientificExportError("Scientific trace sample_count must be positive")
                key = f"trace_{index:03d}_raw"
                if key not in archive:
                    raise ScientificExportError(f"NPZ scientific trace {index} raw samples are missing")
                raw_array = archive[key]
                values = array(typecode)
                try:
                    values.frombytes(raw_array.tobytes())
                except (ValueError, TypeError) as exc:
                    raise ScientificExportError(
                        f"NPZ scientific trace {index} raw dtype is incompatible"
                    ) from exc
                if len(values) != expected:
                    raise ScientificExportError(
                        f"NPZ scientific trace {index} contains {len(values)} samples, "
                        f"expected {expected}"
                    )
                samples_by_index[index] = values
    except ScientificExportError:
        raise
    except Exception as exc:
        raise ScientificExportError(f"Malformed NPZ scientific archive: {exc}") from exc
    return _dataset_from_manifest_and_samples(manifest, samples_by_index)


def import_scientific_dataset(
    path: str | Path,
    *,
    format: ScientificFormat | str | None = None,
) -> ScientificImportResult:
    """Load an A21 archive and reconstruct exact raw waveform data."""
    source = Path(path)
    if not source.is_file():
        raise ScientificExportError(f"Scientific archive does not exist: {source}")
    import_format = infer_scientific_format(source) if format is None else normalize_scientific_format(format)
    started = time.perf_counter()
    if import_format is ScientificFormat.NPZ:
        dataset = _read_npz(source)
    else:
        dataset = _read_dpoz(source)
    duration = max(0.0, time.perf_counter() - started)
    return ScientificImportResult(
        dataset=dataset,
        path=source,
        format=import_format,
        bytes_read=source.stat().st_size,
        duration_s=duration,
    )


__all__ = [
    "SCIENTIFIC_SCHEMA_VERSION",
    "ScientificDataset",
    "ScientificExportError",
    "ScientificExportResult",
    "ScientificFormat",
    "ScientificImportResult",
    "export_scientific_dataset",
    "import_scientific_dataset",
    "infer_scientific_format",
    "normalize_scientific_format",
    "scientific_dataset_from_waveforms",
]
