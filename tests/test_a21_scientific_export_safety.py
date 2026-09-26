from __future__ import annotations

import json
import zipfile
from array import array
from datetime import datetime, timezone

import numpy as np
import pytest

import dpo4000_utils.scientific_export as scientific
from dpo4000_utils.scientific_export import (
    ScientificExportError,
    ScientificFormat,
    export_scientific_dataset,
    import_scientific_dataset,
    scientific_dataset_from_waveforms,
)
from dpo4000_utils.waveform import WaveformData, WaveformPreamble


def waveform(source: str = "CH1", samples: array | None = None) -> WaveformData:
    raw = samples if samples is not None else array("h", [1, 2, 3, 4])
    return WaveformData(
        source=source,
        label=source,
        start_index=1,
        stop_index=len(raw),
        requested_encoding="RIBINARY",
        preamble=WaveformPreamble(
            byte_width=raw.itemsize,
            encoding="BINARY",
            binary_format="RI" if raw.typecode in {"b", "h"} else "RP",
            byte_order="MSB",
            record_point_count=len(raw),
            point_format="Y",
            x_unit="s",
            x_increment=1e-6,
            x_zero=0.0,
            point_offset=0.0,
            y_unit="V",
            y_multiplier=0.01,
            y_offset=0.0,
            y_zero=0.0,
        ),
        samples=raw,
        acquired_at=datetime(2026, 9, 26, tzinfo=timezone.utc),
    )


def test_non_finite_floating_raw_samples_are_rejected() -> None:
    with pytest.raises(ScientificExportError, match="non-finite raw"):
        scientific_dataset_from_waveforms([waveform(samples=array("d", [0.0, float("nan")]))])


def test_trace_and_total_sample_limits_are_enforced(monkeypatch) -> None:
    monkeypatch.setattr(scientific, "MAX_SCIENTIFIC_TRACES", 2)
    with pytest.raises(ScientificExportError, match="cannot exceed 2 traces"):
        scientific_dataset_from_waveforms(
            [waveform("CH1"), waveform("CH2"), waveform("CH3")]
        )

    monkeypatch.setattr(scientific, "MAX_SCIENTIFIC_TRACES", 64)
    monkeypatch.setattr(scientific, "MAX_SCIENTIFIC_SAMPLES", 3)
    with pytest.raises(ScientificExportError, match="total samples"):
        scientific_dataset_from_waveforms([waveform()])


def test_dpoz_rejects_truncated_raw_payload(tmp_path) -> None:
    good = tmp_path / "good.dpoz"
    bad = tmp_path / "bad.dpoz"
    export_scientific_dataset(good, [waveform()], format=ScientificFormat.DPOZ)

    with zipfile.ZipFile(good, "r") as source, zipfile.ZipFile(bad, "w") as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.endswith(".raw"):
                payload = payload[:-1]
            target.writestr(info.filename, payload)

    with pytest.raises(ScientificExportError, match="payload size mismatch"):
        import_scientific_dataset(bad)


def test_dpoz_rejects_unknown_manifest_and_trace_fields(tmp_path) -> None:
    good = tmp_path / "good.dpoz"
    export_scientific_dataset(good, [waveform()])

    for level in ("manifest", "trace"):
        bad = tmp_path / f"unknown-{level}.dpoz"
        with zipfile.ZipFile(good, "r") as source:
            manifest = json.loads(source.read("manifest.json"))
            if level == "manifest":
                manifest["unexpected"] = True
            else:
                manifest["traces"][0]["unexpected"] = True
            with zipfile.ZipFile(bad, "w") as target:
                for info in source.infolist():
                    if info.filename == "manifest.json":
                        target.writestr(info.filename, json.dumps(manifest))
                    else:
                        target.writestr(info.filename, source.read(info.filename))
        with pytest.raises(ScientificExportError, match="unknown fields"):
            import_scientific_dataset(bad)


def test_npz_rejects_raw_dtype_that_disagrees_with_manifest(tmp_path) -> None:
    good = tmp_path / "good.npz"
    bad = tmp_path / "bad.npz"
    export_scientific_dataset(good, [waveform()], format=ScientificFormat.NPZ)

    with np.load(good, allow_pickle=False) as source:
        payload = {name: source[name] for name in source.files}
    payload["trace_000_raw"] = payload["trace_000_raw"].astype(np.int32)
    np.savez(bad, **payload)

    with pytest.raises(ScientificExportError, match="dtype"):
        import_scientific_dataset(bad)


def test_npz_rejects_pickle_object_arrays(tmp_path) -> None:
    path = tmp_path / "object.npz"
    np.savez(path, __manifest_utf8__=np.array([{"unsafe": True}], dtype=object))
    with pytest.raises(ScientificExportError):
        import_scientific_dataset(path)
