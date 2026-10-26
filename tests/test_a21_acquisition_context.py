from __future__ import annotations

from array import array
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from dpo4000_utils.acquisition_context import read_acquisition_context
from dpo4000_utils.control import MeasurementSetup
from dpo4000_utils.errors import DPOTransportError
from dpo4000_utils.scientific_export import (
    ScientificFormat,
    export_scientific_dataset,
    import_scientific_dataset,
)
from dpo4000_utils.waveform import WaveformData, WaveformPreamble


class _Scope:
    def __init__(self, **overrides) -> None:
        self.overrides = overrides

    def get_acquisition_setup(self) -> dict[str, str]:
        return {"mode": "SAMPLE", "stop_after": "RUNSTOP"}

    def get_horizontal_scale(self) -> float:
        value = self.overrides.get("scale", 1e-3)
        if isinstance(value, Exception):
            raise value
        return value

    def get_horizontal_position(self) -> float:
        return 50.0

    def get_record_length(self) -> int:
        return 10_000

    def get_all_measurement_setups(self) -> dict[int, MeasurementSetup]:
        return {
            1: MeasurementSetup(1, "1", "FREQUENCY", "CH1", "", "1.000E3"),
            2: MeasurementSetup(2, "0", "PK2PK", "CH2", "", "5.0"),
            3: MeasurementSetup(3, "ON", "MEAN", "CH1", "", "9.91E37"),
        }


class _ScopeWithUnits(_Scope):
    def read_measurement_unit(self, slot: int) -> str | None:
        if slot == 3:
            raise ValueError("unsupported")
        return {1: "Hz"}.get(slot)


def test_context_records_acquisition_timebase_and_enabled_measurements_only() -> None:
    context = read_acquisition_context(_Scope())
    assert context["version"] == 1
    assert context["acquisition"] == {"mode": "SAMPLE", "stop_after": "RUNSTOP"}
    assert context["horizontal_scale_s_per_div"] == 1e-3
    assert context["horizontal_position"] == 50.0
    assert context["record_length"] == 10_000
    assert [item["slot"] for item in context["measurements"]] == [1, 3]
    first, invalid = context["measurements"]
    assert first == {
        "slot": 1,
        "type": "FREQUENCY",
        "source1": "CH1",
        "source2": "",
        "value_text": "1.000E3",
        "value": 1000.0,
        "unit": None,
    }
    # 9.91E37 is the DPO4000 "no valid measurement" sentinel.
    assert invalid["value"] is None and invalid["value_text"] == "9.91E37"
    assert context["errors"] == {}


def test_units_are_used_when_driver_supports_them_and_failures_are_recorded() -> None:
    context = read_acquisition_context(_ScopeWithUnits())
    units = {item["slot"]: item["unit"] for item in context["measurements"]}
    assert units == {1: "Hz", 3: None}
    assert "MEAS3.unit" in context["errors"]


def test_non_transport_failure_is_recorded_not_raised() -> None:
    context = read_acquisition_context(_Scope(scale=ValueError("garbled")))
    assert context["horizontal_scale_s_per_div"] is None
    assert "horizontal_scale" in context["errors"]
    assert context["record_length"] == 10_000


@pytest.mark.parametrize("value", [float("inf"), float("nan")])
def test_non_finite_timebase_becomes_none(value: float) -> None:
    context = read_acquisition_context(_Scope(scale=value))
    assert context["horizontal_scale_s_per_div"] is None
    assert "non-finite" in context["errors"]["horizontal_scale"]


def test_transport_failure_propagates() -> None:
    with pytest.raises(DPOTransportError):
        read_acquisition_context(_Scope(scale=DPOTransportError("lost")))


def test_measurements_can_be_skipped() -> None:
    assert "measurements" not in read_acquisition_context(_Scope(), include_measurements=False)


def _waveform() -> WaveformData:
    preamble = WaveformPreamble(
        byte_width=2,
        encoding="BINARY",
        binary_format="RI",
        byte_order="MSB",
        record_point_count=4,
        point_format="Y",
        x_unit="s",
        x_increment=1e-6,
        x_zero=0.0,
        point_offset=0.0,
        y_unit="V",
        y_multiplier=0.01,
        y_offset=0.0,
        y_zero=0.0,
    )
    return WaveformData(
        source="CH1",
        label="",
        start_index=1,
        stop_index=4,
        requested_encoding="RIBINARY",
        preamble=preamble,
        samples=array("h", [0, 1, 2, 3]),
        acquired_at=datetime(2026, 10, 25, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize("export_format", [ScientificFormat.NPZ, ScientificFormat.DPOZ])
def test_context_round_trips_through_scientific_export(tmp_path: Path, export_format) -> None:
    if export_format is ScientificFormat.NPZ:
        pytest.importorskip("numpy")
    context = read_acquisition_context(_ScopeWithUnits())
    path = tmp_path / f"data.{export_format.value}"
    export_scientific_dataset(
        path,
        {"CH1": _waveform()},
        format=export_format,
        metadata={"acquisition_context": context},
    )
    loaded = import_scientific_dataset(path)
    assert json.loads(json.dumps(loaded.dataset.metadata["acquisition_context"])) == json.loads(json.dumps(context))
