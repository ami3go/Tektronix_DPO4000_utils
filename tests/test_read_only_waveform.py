"""Offline tests for query-only reads of the preconfigured waveform."""
import pytest

from dpo4000_utils.read_only_guard import ReadOnlyVisaSession
from dpo4000_utils.read_only_waveform import (
    ReadOnlyWaveformUnavailable,
    read_preconfigured_waveform,
)


class ConfiguredScope:
    def __init__(self):
        self.sent = []
        self.points = 3
        self.source = "CH1"
        self.x_increment = "0.001"
        self.samples = [10, 20, 30]

    def query(self, command):
        self.sent.append(command)
        responses = {
            "DATA:SOURCE?": self.source,
            "DATA:START?": "1",
            "DATA:STOP?": "100000",
            "WFMOUTPRE:BYT_NR?": "2",
            "WFMOUTPRE:ENCDG?": "BIN",
            "WFMOUTPRE:BN_FMT?": "RI",
            "WFMOUTPRE:BYT_OR?": "MSB",
            "WFMOUTPRE:NR_PT?": str(self.points),
            "WFMOUTPRE:PT_FMT?": "Y",
            "WFMOUTPRE:XUNIT?": "s",
            "WFMOUTPRE:XINCR?": self.x_increment,
            "WFMOUTPRE:XZERO?": "0",
            "WFMOUTPRE:PT_OFF?": "0",
            "WFMOUTPRE:YUNIT?": "V",
            "WFMOUTPRE:YMULT?": "0.1",
            "WFMOUTPRE:YOFF?": "0",
            "WFMOUTPRE:YZERO?": "0",
            "CH1:LABEL?": "Probe Comp",
        }
        return responses[command]

    def query_binary_values(self, command, **kwargs):
        self.sent.append(command)
        return kwargs["container"](self.samples)

    def write(self, command):
        raise AssertionError(f"Unexpected write: {command}")


def test_configured_waveform_scaling_without_any_setup_commands():
    stub = ConfiguredScope()
    session = ReadOnlyVisaSession(stub)
    wave = read_preconfigured_waveform(session, max_points=3)
    assert wave.source == "CH1"
    assert wave.sample_count == 3
    assert wave.voltage_at(0) == pytest.approx(1.0)
    assert wave.time_at(2) == pytest.approx(0.002)
    assert "CURVE?" in stub.sent
    assert session.blocked_count == 0
    assert all(value.endswith("?") and ";" not in value for value in stub.sent)
    assert not any(value.startswith("DATA:") and not value.endswith("?") for value in stub.sent)


def test_preconfigured_window_over_maximum_is_skip_not_truncate():
    stub = ConfiguredScope()
    stub.points = 10_001
    session = ReadOnlyVisaSession(stub)
    with pytest.raises(ReadOnlyWaveformUnavailable, match="ceiling"):
        read_preconfigured_waveform(session, max_points=1000)
    assert "CURVE?" not in stub.sent


def test_unavailable_source_is_not_reconfigured():
    stub = ConfiguredScope()
    stub.source = "MATH"
    session = ReadOnlyVisaSession(stub)
    with pytest.raises(ReadOnlyWaveformUnavailable, match="not an analog"):
        read_preconfigured_waveform(session)
    assert stub.sent == ["DATA:SOURCE?"]


def test_malformed_scaling_is_reported_as_error():
    stub = ConfiguredScope()
    stub.x_increment = "nan"
    with pytest.raises(Exception, match="Non-finite|Invalid"):
        read_preconfigured_waveform(ReadOnlyVisaSession(stub))
    assert "CURVE?" not in stub.sent


def test_unprotected_instrument_is_rejected():
    with pytest.raises(TypeError, match="protected"):
        read_preconfigured_waveform(ConfiguredScope())
