import csv

import pytest

from dpo4000_utils.waveform import (
    enabled_channels,
    normalize_channel_label,
    parse_ascii_curve,
    parse_channel_enabled,
    read_channel_waveform,
    read_enabled_channel_waveforms,
    save_enabled_channels_to_single_csv,
    scale_waveform_samples,
    validate_channel,
    write_multi_channel_csv,
)


class FakeScope:
    def __init__(self, responses):
        self.responses = dict(responses)
        self.writes = []
        self.queries = []

    def write(self, command):
        self.writes.append(command)

    def query(self, command):
        self.queries.append(command)
        response = self.responses.get(command)
        if isinstance(response, list):
            return response.pop(0)
        if response is None:
            raise AssertionError(f"Unexpected query: {command}")
        return response


def test_validate_channel_accepts_only_1_to_4():
    assert validate_channel("1") == 1
    assert validate_channel(4) == 4
    with pytest.raises(ValueError):
        validate_channel(0)
    with pytest.raises(ValueError):
        validate_channel(5)


def test_parse_ascii_curve():
    assert parse_ascii_curve("1, 2.5, -3\n") == [1.0, 2.5, -3.0]


def test_parse_channel_enabled():
    assert parse_channel_enabled("1")
    assert parse_channel_enabled("ON")
    assert not parse_channel_enabled("0")
    assert not parse_channel_enabled("OFF")


def test_normalize_channel_label():
    assert normalize_channel_label('"Input A"', 1) == "Input A"
    assert normalize_channel_label("", 2) == "CH2"


def test_scale_waveform_samples():
    times, volts = scale_waveform_samples(
        [10, 11, 12],
        x_increment=0.5,
        x_origin=1.0,
        y_multiplier=0.1,
        y_offset=10.0,
        y_zero=-1.0,
    )
    assert times == [1.0, 1.5, 2.0]
    assert volts == [-1.0, -0.9, -0.8]


def test_read_channel_waveform_queries_expected_scope_commands():
    scope = FakeScope(
        {
            "CURVE?": "10,11,12",
            "WFMPRE:XINCR?": "0.5",
            "WFMPRE:XZERO?": "1.0",
            "WFMPRE:YMULT?": "0.1",
            "WFMPRE:YOFF?": "10",
            "WFMPRE:YZERO?": "-1",
        }
    )

    times, volts = read_channel_waveform(scope, 3)

    assert scope.writes == ["DATA:SOURCE CH3", "DATA:ENC ASCII"]
    assert times == [1.0, 1.5, 2.0]
    assert volts == [-1.0, -0.9, -0.8]


def test_enabled_channels_queries_all_candidates():
    scope = FakeScope(
        {
            "SELECT:CH1?": "1",
            "SELECT:CH2?": "0",
            "SELECT:CH3?": "ON",
            "SELECT:CH4?": "OFF",
        }
    )
    assert enabled_channels(scope) == [1, 3]


def test_read_enabled_channel_waveforms_uses_labels():
    scope = FakeScope(
        {
            "SELECT:CH1?": "1",
            "SELECT:CH2?": "0",
            "SELECT:CH3?": "0",
            "SELECT:CH4?": "0",
            "CURVE?": "10,11",
            "WFMPRE:XINCR?": "1",
            "WFMPRE:XZERO?": "0",
            "WFMPRE:YMULT?": "0.5",
            "WFMPRE:YOFF?": "10",
            "WFMPRE:YZERO?": "0",
            "CH1:LABEL?": '"VBUS"',
        }
    )

    times, channel_data = read_enabled_channel_waveforms(scope)

    assert times == [0.0, 1.0]
    assert channel_data == {"VBUS": [0.0, 0.5]}


def test_read_enabled_channel_waveforms_requires_enabled_channel():
    scope = FakeScope(
        {
            "SELECT:CH1?": "0",
            "SELECT:CH2?": "0",
            "SELECT:CH3?": "0",
            "SELECT:CH4?": "0",
        }
    )
    with pytest.raises(RuntimeError, match="No enabled channels"):
        read_enabled_channel_waveforms(scope)


def test_write_multi_channel_csv(tmp_path):
    path = tmp_path / "waveforms.csv"
    write_multi_channel_csv(path, [0.0, 1.0], {"CH1": [1.0, 2.0], "CH2": [3.0, 4.0]})

    with path.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.reader(csv_file))

    assert rows == [
        ["Time (s)", "CH1", "CH2"],
        ["0.0", "1.0", "3.0"],
        ["1.0", "2.0", "4.0"],
    ]


def test_save_enabled_channels_to_single_csv(tmp_path):
    scope = FakeScope(
        {
            "SELECT:CH1?": "1",
            "SELECT:CH2?": "0",
            "SELECT:CH3?": "0",
            "SELECT:CH4?": "0",
            "CURVE?": "1,2",
            "WFMPRE:XINCR?": "1",
            "WFMPRE:XZERO?": "0",
            "WFMPRE:YMULT?": "1",
            "WFMPRE:YOFF?": "0",
            "WFMPRE:YZERO?": "0",
            "CH1:LABEL?": "",
        }
    )
    path = tmp_path / "combined.csv"

    assert save_enabled_channels_to_single_csv(scope, path) == path
    assert path.read_text(encoding="utf-8").splitlines()[0] == "Time (s),CH1"
