from __future__ import annotations

import json
import math
import zipfile
from array import array
from datetime import datetime, timezone

import numpy as np
import pytest

import dpo4000_utils.scientific_export as scientific
from dpo4000_utils.scientific_export import (
    ScientificDataset,
    ScientificExportError,
    ScientificFormat,
    export_scientific_dataset,
    import_scientific_dataset,
    infer_scientific_format,
    normalize_scientific_format,
    scientific_dataset_from_waveforms,
)
from dpo4000_utils.waveform import WaveformData, WaveformPreamble


def make_waveform(
    source: str = "CH1",
    *,
    samples: array | None = None,
    x_zero: float = -1e-3,
    x_increment: float = 1e-6,
    y_multiplier: float = 0.01,
    y_offset: float = 0.0,
    y_zero: float = 0.0,
) -> WaveformData:
    raw = samples if samples is not None else array("h", [-100, 0, 100, 200])
    count = len(raw)
    return WaveformData(
        source=source,
        label=f"{source} label",
        start_index=1,
        stop_index=count,
        requested_encoding="RIBINARY",
        preamble=WaveformPreamble(
            byte_width=raw.itemsize,
            encoding="BINARY",
            binary_format="RI" if raw.typecode in {"b", "h"} else "RP",
            byte_order="MSB",
            record_point_count=count,
            point_format="Y",
            x_unit="s",
            x_increment=x_increment,
            x_zero=x_zero,
            point_offset=0.0,
            y_unit="V",
            y_multiplier=y_multiplier,
            y_offset=y_offset,
            y_zero=y_zero,
        ),
        samples=raw,
        acquired_at=datetime(2026, 9, 26, 18, 0, tzinfo=timezone.utc),
    )


def assert_waveform_equal(left: WaveformData, right: WaveformData) -> None:
    assert left.source == right.source
    assert left.label == right.label
    assert left.start_index == right.start_index
    assert left.stop_index == right.stop_index
    assert left.requested_encoding == right.requested_encoding
    assert left.preamble == right.preamble
    assert left.samples.typecode == right.samples.typecode
    assert left.samples.tolist() == right.samples.tolist()
    assert left.acquired_at == right.acquired_at


def test_format_normalization_and_inference() -> None:
    assert normalize_scientific_format("npz") is ScientificFormat.NPZ
    assert normalize_scientific_format(".npz") is ScientificFormat.NPZ
    assert normalize_scientific_format("numpy") is ScientificFormat.NPZ
    assert normalize_scientific_format("portable") is ScientificFormat.DPOZ
    assert infer_scientific_format("capture.npz") is ScientificFormat.NPZ
    assert infer_scientific_format("capture.dpoz") is ScientificFormat.DPOZ
    assert infer_scientific_format("capture.zip") is ScientificFormat.DPOZ
    with pytest.raises(ScientificExportError):
        normalize_scientific_format("mat")
    with pytest.raises(ScientificExportError):
        infer_scientific_format("capture.csv")


def test_dataset_rejects_duplicate_sources_bad_metadata_and_inconsistent_waveform() -> None:
    waveform = make_waveform()
    with pytest.raises(ScientificExportError, match="duplicate source"):
        ScientificDataset(
            (waveform, make_waveform()),
            {},
            datetime.now(timezone.utc),
        )
    with pytest.raises(ScientificExportError, match="non-finite"):
        scientific_dataset_from_waveforms([waveform], metadata={"bad": math.nan})
    with pytest.raises(ScientificExportError, match="metadata"):
        ScientificDataset((waveform,), None, datetime.now(timezone.utc))  # type: ignore[arg-type]

    bad = make_waveform(samples=array("h", [1, 2, 3]))
    bad.stop_index = 4
    with pytest.raises(ScientificExportError, match="sample count"):
        scientific_dataset_from_waveforms([bad])


def test_npz_round_trip_preserves_raw_data_and_exposes_scientific_arrays(tmp_path) -> None:
    first = make_waveform("CH1")
    second = make_waveform(
        "CH2",
        samples=array("H", [0, 10, 20, 30]),
        y_multiplier=0.02,
        y_zero=-1.0,
    )
    output = tmp_path / "waveforms.npz"
    result = export_scientific_dataset(
        output,
        [first, second],
        metadata={"test": "round-trip", "number": 7},
    )
    assert result.path == output
    assert result.format is ScientificFormat.NPZ
    assert result.trace_count == 2
    assert result.sample_count == 8
    assert result.bytes_written > 0
    assert result.duration_s >= 0
    assert result.samples_per_second > 0
    assert result.megabytes_per_second > 0

    with np.load(output, allow_pickle=False) as archive:
        assert "trace_000_raw" in archive
        assert "trace_000_x" in archive
        assert "trace_000_y" in archive
        np.testing.assert_allclose(
            archive["trace_000_x"],
            np.array([first.time_at(index) for index in range(first.sample_count)]),
        )
        np.testing.assert_allclose(
            archive["trace_000_y"],
            np.array([first.voltage_at(index) for index in range(first.sample_count)]),
        )

    loaded = import_scientific_dataset(output)
    assert loaded.format is ScientificFormat.NPZ
    assert loaded.dataset.metadata == {"test": "round-trip", "number": 7}
    assert loaded.dataset.trace_count == 2
    assert loaded.dataset.sample_count == 8
    assert loaded.bytes_read == output.stat().st_size
    assert_waveform_equal(first, loaded.dataset.by_source()["CH1"])
    assert_waveform_equal(second, loaded.dataset.by_source()["CH2"])


def test_dpoz_round_trip_contains_manifest_raw_and_csv(tmp_path) -> None:
    waveform = make_waveform("CH1")
    output = tmp_path / "waveforms.dpoz"
    export_scientific_dataset(
        output,
        [waveform],
        metadata={"operator": "test"},
        compressed=True,
    )

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "traces/000_CH1.raw" in names
        assert "traces/000_CH1.csv" in names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["schema"] == "dpo4000-scientific"
        assert manifest["format"] == "dpoz"
        csv_text = archive.read("traces/000_CH1.csv").decode("utf-8")
        assert csv_text.startswith("index,x (s),y (V)")
        assert len(csv_text.splitlines()) == waveform.sample_count + 1

    loaded = import_scientific_dataset(output)
    assert loaded.format is ScientificFormat.DPOZ
    assert loaded.dataset.metadata == {"operator": "test"}
    assert_waveform_equal(waveform, loaded.dataset.waveforms[0])


def test_export_is_atomic_and_preserves_existing_destination_on_failure(tmp_path, monkeypatch) -> None:
    output = tmp_path / "existing.dpoz"
    output.write_bytes(b"previous-good-file")

    def fail_writer(temp_path, dataset, *, compressed):
        temp_path.write_bytes(b"partial")
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr(scientific, "_write_dpoz", fail_writer)
    with pytest.raises(RuntimeError, match="simulated"):
        export_scientific_dataset(output, [make_waveform()])
    assert output.read_bytes() == b"previous-good-file"
    assert not list(tmp_path.glob(".existing.dpoz.*.tmp"))


def test_import_rejects_missing_or_malformed_archives(tmp_path) -> None:
    with pytest.raises(ScientificExportError, match="does not exist"):
        import_scientific_dataset(tmp_path / "missing.npz")

    bad_zip = tmp_path / "bad.dpoz"
    bad_zip.write_bytes(b"not a zip")
    with pytest.raises(ScientificExportError, match="Malformed"):
        import_scientific_dataset(bad_zip)

    wrong_schema = tmp_path / "wrong.dpoz"
    with zipfile.ZipFile(wrong_schema, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"schema": "other", "schema_version": 1, "traces": [{}]}),
        )
    with pytest.raises(ScientificExportError, match="schema identifier"):
        import_scientific_dataset(wrong_schema)


def test_100k_npz_round_trip_scaling_smoke(tmp_path) -> None:
    samples = array("h", (index % 2000 - 1000 for index in range(100_000)))
    waveform = make_waveform("CH1", samples=samples)
    output = tmp_path / "large.npz"
    exported = export_scientific_dataset(output, [waveform])
    imported = import_scientific_dataset(output)
    assert exported.sample_count == 100_000
    assert imported.dataset.sample_count == 100_000
    assert imported.dataset.waveforms[0].samples[0] == samples[0]
    assert imported.dataset.waveforms[0].samples[-1] == samples[-1]
