"""A21 scientific export round-trip qualification against a real DPO4054."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from dpo4000_utils import DPO4054
from dpo4000_utils.connection import visaResourceAddr
from dpo4000_utils.scientific_export import (
    ScientificFormat,
    export_scientific_dataset,
    import_scientific_dataset,
)

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


@pytest.fixture(scope="module")
def a21_scope() -> Iterator[DPO4054]:
    if not _env_enabled("DPO4000_HARDWARE"):
        pytest.skip("Set DPO4000_HARDWARE=1 to run A21 hardware qualification.")
    resource = os.getenv("DPO4000_RESOURCE", visaResourceAddr).strip()
    if not resource:
        pytest.skip("Set DPO4000_RESOURCE to the oscilloscope VISA resource.")
    scope = DPO4054(
        resource,
        auto_connect=False,
        timeout_ms=int(os.getenv("DPO4000_TIMEOUT_MS", "20000")),
    )
    scope.connect()
    try:
        identity = scope.query_identity()
        expected = os.getenv("DPO4000_EXPECT_IDN", "TEKTRONIX,DPO4054").strip()
        assert expected.upper() in identity.upper()
        yield scope
    finally:
        scope.disconnect()


def _assert_round_trip(original, loaded) -> None:
    assert loaded.source == original.source
    assert loaded.label == original.label
    assert loaded.start_index == original.start_index
    assert loaded.stop_index == original.stop_index
    assert loaded.preamble == original.preamble
    assert loaded.samples.typecode == original.samples.typecode
    assert loaded.samples.tolist() == original.samples.tolist()


@pytest.mark.hardware
def test_a21_real_waveform_npz_and_dpoz_round_trip(a21_scope: DPO4054, tmp_path) -> None:
    waveform = a21_scope.read_channel_waveform_data(1, point_count=1000)
    assert waveform.sample_count == 1000

    for export_format, suffix in (
        (ScientificFormat.NPZ, ".npz"),
        (ScientificFormat.DPOZ, ".dpoz"),
    ):
        output = tmp_path / f"dpo4054_a21{suffix}"
        exported = export_scientific_dataset(
            output,
            [waveform],
            format=export_format,
            metadata={"scope_identity": a21_scope.query_identity()},
        )
        imported = import_scientific_dataset(output)
        assert exported.sample_count == 1000
        assert exported.bytes_written > 0
        assert imported.dataset.sample_count == 1000
        _assert_round_trip(waveform, imported.dataset.waveforms[0])
