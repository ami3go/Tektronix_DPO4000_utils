from __future__ import annotations

from pathlib import Path

import pytest

from dpo4000_utils.advanced_trigger import CapabilityProbeResult
from dpo4000_utils.baseline_capture import (
    NOT_YET_COVERED,
    BaselineConfig,
    HardwareBaselineCapture,
    distribution,
)
from dpo4000_utils.control import MeasurementSetup


def test_distribution_computes_known_percentiles():
    stats = distribution([1.0, 2.0, 3.0, 4.0, 5.0])
    assert stats == {
        "min": 1.0,
        "p50": 3.0,
        "p95": 5.0,
        "p99": 5.0,
        "max": 5.0,
        "sample_count": 5,
    }


def test_distribution_single_sample_is_degenerate():
    stats = distribution([0.25])
    assert stats["min"] == stats["p50"] == stats["p95"] == stats["p99"] == stats["max"] == 0.25
    assert stats["sample_count"] == 1


def test_distribution_rejects_empty_input():
    with pytest.raises(ValueError):
        distribution([])


class FakeWaveform:
    def __init__(self, *, sample_count: int) -> None:
        self.sample_count = sample_count


class FakeInstrument:
    def __init__(self) -> None:
        self.timeout = 1_000


class FakeScope:
    def __init__(
        self,
        resource,
        *,
        auto_connect: bool = False,
        timeout_ms=None,
        read_termination=None,
        write_termination=None,
    ) -> None:
        self.resource = resource
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.record_length = 1_000
        self.acquiring = False
        self._instrument = FakeInstrument()
        self.trigger_configure_calls = 0
        self.probe_calls: list[tuple[str, int]] = []

    def connect(self) -> None:
        self.connect_calls += 1

    def disconnect(self) -> None:
        self.disconnect_calls += 1

    def ensure_connected(self):
        return self._instrument

    def query_identity(self) -> str:
        return "TEKTRONIX,DPO4054,FAKE,CF:00.0CT FV:v0.00"

    def get_channel_configuration(self, channel):
        return {"display": "1", "scale": "0.5", "position": "0"}

    def configure_channel(self, config) -> None:
        return None

    def get_available_reference_slots(self):
        return (1,)

    def get_reference_configuration(self, slot):
        return {"display": "0"}

    def get_available_bus_slots(self):
        return ()

    def get_bus_configuration(self, slot):
        return {}

    def get_all_measurement_setups(self):
        return {1: MeasurementSetup(slot=1, state="OFF")}

    def get_math_configuration(self):
        return {"display": "0"}

    def get_edge_trigger_configuration(self):
        return {"source": "CH1"}

    def get_trigger_configuration(self):
        return {"trigger_type": "PULSE", "pulse_class": "WIDTH", "holdoff": 1e-6}

    def configure_trigger(self, config, *, holdoff=None) -> None:
        self.trigger_configure_calls += 1

    def get_trigger_holdoff(self):
        return 1e-6

    def probe_scpi_query(self, command: str, *, timeout_ms: int = 500):
        self.probe_calls.append((command, timeout_ms))
        return CapabilityProbeResult(
            query=command,
            supported=False,
            timed_out=True,
            recovered=True,
        )

    def get_trigger_level(self, channel=None):
        return 0.0

    def get_horizontal_position(self):
        return 0.0

    def get_record_length(self):
        return self.record_length

    def set_record_length(self, value) -> None:
        self.record_length = int(value)

    def get_acquisition_setup(self):
        return {"mode": "SAMPLE"}

    def get_display_settings(self):
        return {"intensity": "50"}

    def single_acquisition(self) -> None:
        self.acquiring = False

    def is_acquiring(self) -> bool:
        return self.acquiring

    def save_image_path(self, path):
        Path(path).write_bytes(b"\x89PNG\r\n")
        return Path(path)

    def save_all_channels_to_single_csv(self, path):
        Path(path).write_text("t,ch1\n")
        return Path(path)

    def read_channel_waveform_data(self, channel, **kwargs):
        return FakeWaveform(sample_count=self.record_length)


def _fake_setup_round_trip(monkeypatch):
    monkeypatch.setattr(
        "dpo4000_utils.baseline_capture.build_scope_settings_payload",
        lambda instrument: {"instrument": "FAKE", "setup": ":SET 1"},
    )
    monkeypatch.setattr(
        "dpo4000_utils.baseline_capture.apply_setup_string",
        lambda instrument, setup, **kwargs: None,
    )


def _config(tmp_path, **overrides):
    defaults = dict(
        resource="FAKE::INSTR",
        output_dir=tmp_path,
        reps_standard=2,
        reps_heavy=1,
        reps_waveform_large=1,
    )
    defaults.update(overrides)
    return BaselineConfig(**defaults)


def test_capture_functional_smoke(tmp_path, monkeypatch):
    _fake_setup_round_trip(monkeypatch)
    capture = HardwareBaselineCapture(_config(tmp_path))
    capture.scope = FakeScope("FAKE::INSTR")

    result = capture.capture_functional()

    assert result["connection"]["idn"].startswith("TEKTRONIX")
    assert set(result["channels"]) == {"1", "2", "3", "4"}
    assert result["references"] == {"1": {"display": "0"}}
    assert result["buses"] == {"available": False}
    assert result["measurements"]["1"]["slot"] == 1
    assert result["setup_round_trip"] == {"restored": True, "instrument_matches": True}


def test_capture_timing_smoke(tmp_path, monkeypatch):
    _fake_setup_round_trip(monkeypatch)
    monkeypatch.setattr("dpo4000_utils.baseline_capture.DPO4054", FakeScope)
    capture = HardwareBaselineCapture(
        _config(
            tmp_path,
            waveform_sizes=(100, 1_000),
            connection_settle_delay_s=0.0,
            capability_probe_timeout_ms=125,
        )
    )
    capture.scope = FakeScope("FAKE::INSTR")

    result = capture.capture_timing()

    for key in (
        "connection",
        "channel_apply",
        "measurement_refresh",
        "trigger_config_apply",
        "trigger_config_readback",
        "unsupported_trigger_probe",
        "single_acquisition",
        "png_capture",
        "csv_export",
    ):
        assert result[key]["sample_count"] > 0
    assert result["unsupported_trigger_probe"]["probe_timeout_ms"] == 125
    assert set(result["waveform_acquisition"]) == {"100", "1000"}
    assert result["not_yet_covered"] == list(NOT_YET_COVERED)
