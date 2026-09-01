from __future__ import annotations

import csv
import struct
from array import array
from datetime import datetime, timezone

import pytest

from dpo4000_utils.errors import DPOWaveformError
from dpo4000_utils.waveform import (
    FULL_WAVEFORM_STOP,
    WaveformData,
    WaveformPreamble,
    WaveformRequest,
    decode_binary_samples,
    enabled_channels,
    normalize_channel_label,
    normalize_waveform_encoding,
    normalize_waveform_source,
    parse_ascii_curve,
    parse_channel_enabled,
    parse_ieee_block_payload,
    read_channel_waveform,
    read_enabled_channel_waveforms,
    read_waveform,
    scale_waveform_samples,
    validate_waveform_alignment,
    write_multi_channel_csv,
    write_waveforms_csv,
)


def _base_preamble(**overrides):
    values = {
        "byte_width": 2,
        "encoding": "BIN",
        "binary_format": "RI",
        "byte_order": "MSB",
        "record_point_count": 3,
        "point_format": "Y",
        "x_unit": "s",
        "x_increment": 0.5,
        "x_zero": 1.0,
        "point_offset": 0.0,
        "y_unit": "V",
        "y_multiplier": 0.1,
        "y_offset": 10.0,
        "y_zero": -1.0,
    }
    values.update(overrides)
    return WaveformPreamble(**values)


class BinaryScope:
    def __init__(self, samples=(10, 11, 12), *, record_length=100, responses=None):
        self.samples = tuple(samples)
        self.record_length = record_length
        self.data_start = 1
        self.data_stop = min(len(self.samples), record_length) if self.samples else 1
        self.current_source = "CH1"
        self.encoding = "RIBINARY"
        self.width = 2
        self.read_termination = "\n"
        self.events = []
        self.writes = []
        self.queries = []
        self.binary_calls = []
        self.responses = {
            "WFMOUTPRE:BYT_NR?": lambda: str(self.width),
            "WFMOUTPRE:ENCDG?": lambda: "ASC" if self.encoding == "ASCII" else "BIN",
            "WFMOUTPRE:BN_FMT?": "RI",
            "WFMOUTPRE:BYT_OR?": "MSB",
            "WFMOUTPRE:NR_PT?": lambda: str(self.data_stop - self.data_start + 1),
            "WFMOUTPRE:PT_FMT?": "Y",
            "WFMOUTPRE:XUNIT?": '"s"',
            "WFMOUTPRE:XINCR?": "0.5",
            "WFMOUTPRE:XZERO?": "1.0",
            "WFMOUTPRE:PT_OFF?": "0",
            "WFMOUTPRE:YUNIT?": '"V"',
            "WFMOUTPRE:YMULT?": "0.1",
            "WFMOUTPRE:YOFF?": "10",
            "WFMOUTPRE:YZERO?": "-1",
            "CH1:LABEL?": '"Voltage"',
            "CH2:LABEL?": '"Voltage"',
            "CH3:LABEL?": '"Input"',
            "CH4:LABEL?": '"CH4"',
        }
        if responses:
            self.responses.update(responses)

    def write(self, command):
        self.events.append(("write", command))
        self.writes.append(command)
        if command.startswith("DATA:SOURCE "):
            self.current_source = command.split()[-1]
        elif command.startswith("DATA:START "):
            requested = int(command.split()[-1])
            self.data_start = min(max(1, requested), self.record_length)
            if self.data_stop < self.data_start:
                self.data_stop = self.data_start
        elif command.startswith("DATA:STOP "):
            requested = int(command.split()[-1])
            self.data_stop = min(max(1, requested), self.record_length)
            if self.data_stop < self.data_start:
                self.data_start, self.data_stop = self.data_stop, self.data_start
        elif command.startswith("DATA:WIDTH "):
            self.width = int(command.split()[-1])
        elif command.startswith("DATA:ENCDG "):
            self.encoding = command.split()[-1]

    def query(self, command):
        self.events.append(("query", command))
        self.queries.append(command)
        if command == "DATA:START?":
            return str(self.data_start)
        if command == "DATA:STOP?":
            return str(self.data_stop)
        if command.startswith("SELECT:CH"):
            return self.responses.get(command, "0")
        if command == "CURVE?" and self.encoding == "ASCII":
            count = self.data_stop - self.data_start + 1
            return ":CURVE " + ",".join(str(x) for x in self.samples[:count])
        value = self.responses.get(command)
        if callable(value):
            return value()
        if value is None:
            raise AssertionError(f"Unexpected query: {command}")
        return value

    def query_binary_values(self, message, **kwargs):
        self.events.append(("binary", message))
        self.binary_calls.append((message, kwargs))
        count = self.data_stop - self.data_start + 1
        return kwargs["container"](self.samples[:count])


def _waveform(source="CH1", label="Voltage", samples=(10, 11), **preamble_overrides):
    return WaveformData(
        source=source,
        label=label,
        start_index=1,
        stop_index=len(samples),
        requested_encoding="RIBINARY",
        preamble=_base_preamble(record_point_count=len(samples), **preamble_overrides),
        samples=array("h", samples),
        acquired_at=datetime.now(timezone.utc),
    )


def test_source_and_encoding_normalization():
    assert normalize_waveform_source(1) == "CH1"
    assert normalize_waveform_source("math1") == "MATH"
    assert normalize_waveform_source("ref4") == "REF4"
    assert normalize_waveform_encoding("ri") == "RIBINARY"
    assert normalize_waveform_encoding("asc") == "ASCII"
    with pytest.raises(ValueError):
        normalize_waveform_source("BUS1")
    with pytest.raises(ValueError):
        normalize_waveform_encoding("JSON")


def test_ascii_and_ieee_parsers_are_strict():
    assert parse_ascii_curve(":CURVE 1,2.5,-3\n") == [1.0, 2.5, -3.0]
    with pytest.raises(DPOWaveformError, match="Malformed ASCII"):
        parse_ascii_curve("CURVE 1,bad,3")
    assert parse_ieee_block_payload(b":CURVE #14abcd\n") == b"abcd"
    with pytest.raises(DPOWaveformError, match="Truncated IEEE waveform block"):
        parse_ieee_block_payload(b"#14ab")


def test_binary_decoder_supports_signed_msb_and_unsigned_lsb_words():
    assert list(
        decode_binary_samples(
            struct.pack(">hhh", -1, 0, 32767),
            sample_width=2,
            signed=True,
            byte_order="MSB",
        )
    ) == [-1, 0, 32767]
    assert list(
        decode_binary_samples(
            struct.pack("<HH", 0, 65535),
            sample_width=2,
            signed=False,
            byte_order="LSB",
        )
    ) == [0, 65535]


def test_explicit_transfer_configures_and_verifies_scope_range_before_preamble():
    scope = BinaryScope(samples=(10, 11, 12), record_length=100)
    waveform = read_waveform(scope, WaveformRequest(source=3, start_index=1, stop_index=3))
    assert scope.writes[:5] == [
        "DATA:SOURCE CH3",
        "DATA:START 1",
        "DATA:STOP 3",
        "DATA:WIDTH 2",
        "DATA:ENCDG RIBINARY",
    ]
    assert scope.queries.index("DATA:START?") < scope.queries.index("WFMOUTPRE:BYT_NR?")
    assert scope.queries.index("DATA:STOP?") < scope.queries.index("WFMOUTPRE:BYT_NR?")
    assert waveform.source == "CH3"
    assert waveform.sample_count == 3
    assert list(waveform.iter_times()) == [1.0, 1.5, 2.0]
    assert list(waveform.iter_voltages()) == pytest.approx([-1.0, -0.9, -0.8])


def test_partial_transfer_uses_xzero_as_first_outgoing_point():
    scope = BinaryScope(samples=(10, 11), record_length=10)
    waveform = read_waveform(
        scope,
        WaveformRequest(source="CH1", start_index=3, point_count=2),
    )
    assert waveform.start_index == 3
    assert waveform.stop_index == 4
    assert list(waveform.iter_times()) == [1.0, 1.5]


def test_default_full_range_ignores_stale_nr_pt_and_uses_scope_clipped_stop():
    scope = BinaryScope(samples=tuple(range(8)), record_length=8)
    scope.data_start = 3
    scope.data_stop = 4
    waveform = read_waveform(scope, WaveformRequest(source="CH1"))
    assert f"DATA:STOP {FULL_WAVEFORM_STOP}" in scope.writes
    assert waveform.start_index == 1
    assert waveform.stop_index == 8
    assert waveform.sample_count == 8
    assert scope.queries.count("WFMOUTPRE:NR_PT?") == 1


def test_explicit_range_clipping_is_rejected_instead_of_silently_shortening():
    scope = BinaryScope(samples=(10, 11, 12), record_length=3)
    with pytest.raises(DPOWaveformError, match="adjusted DATA:STOP"):
        read_waveform(scope, WaveformRequest(source="CH1", start_index=1, stop_index=4))


def test_preamble_nr_pt_is_transfer_count_not_absolute_stop_index():
    scope = BinaryScope(samples=(10, 11), record_length=10)
    waveform = read_waveform(
        scope,
        WaveformRequest(source="CH1", start_index=3, stop_index=4),
    )
    assert waveform.preamble.record_point_count == 2
    assert waveform.sample_count == 2


def test_preamble_count_mismatch_is_protocol_error():
    scope = BinaryScope(
        samples=(10, 11),
        record_length=10,
        responses={"WFMOUTPRE:NR_PT?": "99"},
    )
    with pytest.raises(DPOWaveformError, match="Outgoing waveform count"):
        read_waveform(scope, WaveformRequest(source="CH1", start_index=3, stop_index=4))


def test_waveform_sample_count_mismatch_is_protocol_error():
    scope = BinaryScope(samples=(10, 11), record_length=10)
    with pytest.raises(DPOWaveformError, match="point-count mismatch"):
        read_waveform(scope, WaveformRequest(source="CH1", start_index=1, stop_index=3))


def test_ascii_is_explicit_compatibility_path():
    scope = BinaryScope(samples=(10, 11), record_length=2)
    waveform = read_waveform(
        scope,
        WaveformRequest(source="CH1", stop_index=2, encoding="ASCII"),
    )
    assert "DATA:ENCDG ASCII" in scope.writes
    assert not scope.binary_calls
    assert list(waveform.samples) == [10.0, 11.0]


def test_scale_helper_treats_x_origin_as_first_outgoing_point_even_for_partial_range():
    times, volts = scale_waveform_samples(
        [10, 11],
        x_increment=0.5,
        x_origin=1.0,
        y_multiplier=0.1,
        y_offset=10,
        y_zero=-1,
        start_index=3,
    )
    assert times == [1.0, 1.5]
    assert volts == pytest.approx([-1.0, -0.9])


def test_legacy_channel_wrapper_returns_lists():
    scope = BinaryScope(samples=(10, 11), record_length=2)
    times, volts = read_channel_waveform(scope, 1)
    assert times == [1.0, 1.5]
    assert volts == pytest.approx([-1.0, -0.9])


def test_channel_helpers_accept_verbose_values():
    assert parse_channel_enabled(":SELECT:CH1 1")
    assert not parse_channel_enabled(":SELECT:CH2 0")
    assert normalize_channel_label(':CH1:LABEL "Input A"', 1) == "Input A"
    assert normalize_channel_label("", 2) == "CH2"


def test_enabled_channels_queries_candidates():
    scope = BinaryScope(
        responses={
            "SELECT:CH1?": "1",
            "SELECT:CH2?": "0",
            "SELECT:CH3?": "ON",
            "SELECT:CH4?": "OFF",
        }
    )
    assert enabled_channels(scope) == [1, 3]


def test_duplicate_labels_remain_distinct_in_legacy_multi_channel_wrapper():
    scope = BinaryScope(
        samples=(10, 11),
        record_length=2,
        responses={
            "SELECT:CH1?": "1",
            "SELECT:CH2?": "1",
            "SELECT:CH3?": "0",
            "SELECT:CH4?": "0",
            "CH1:LABEL?": '"Voltage"',
            "CH2:LABEL?": '"Voltage"',
        },
    )
    times, channel_data = read_enabled_channel_waveforms(scope)
    assert times == [1.0, 1.5]
    assert set(channel_data) == {"CH1 Voltage", "CH2 Voltage"}


def test_structured_csv_keeps_duplicate_labels_distinct(tmp_path):
    path = tmp_path / "waveforms.csv"
    write_waveforms_csv(path, [_waveform("CH1", "Voltage"), _waveform("CH2", "Voltage")])
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["Time (s)", "CH1 Voltage", "CH2 Voltage"]


def test_alignment_rejects_length_or_axis_mismatch():
    reference = _waveform("CH1", "A", (10, 11))
    with pytest.raises(DPOWaveformError, match="sample-count mismatch"):
        validate_waveform_alignment([reference, _waveform("CH2", "B", (10,))])
    with pytest.raises(DPOWaveformError, match="X-axis mismatch"):
        validate_waveform_alignment(
            [reference, _waveform("CH2", "B", (10, 11), x_increment=0.6)]
        )


def test_legacy_multi_channel_csv_rejects_mismatched_lengths(tmp_path):
    with pytest.raises(DPOWaveformError, match="expected 2"):
        write_multi_channel_csv(
            tmp_path / "bad.csv",
            [0.0, 1.0],
            {"CH1": [1.0, 2.0], "CH2": [3.0]},
        )
