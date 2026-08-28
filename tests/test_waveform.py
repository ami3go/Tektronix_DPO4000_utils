from __future__ import annotations

import csv
import struct
from array import array
from datetime import datetime, timezone

import pytest

from dpo4000_utils.errors import DPOWaveformError
from dpo4000_utils.waveform import (
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
        "record_point_count": 100,
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


def _preamble_responses(**overrides):
    values = {
        "WFMOUTPRE:BYT_NR?": "2",
        "WFMOUTPRE:ENCDG?": "BIN",
        "WFMOUTPRE:BN_FMT?": "RI",
        "WFMOUTPRE:BYT_OR?": "MSB",
        "WFMOUTPRE:NR_PT?": "100",
        "WFMOUTPRE:PT_FMT?": "Y",
        "WFMOUTPRE:XUNIT?": '"s"',
        "WFMOUTPRE:XINCR?": "0.5",
        "WFMOUTPRE:XZERO?": "1.0",
        "WFMOUTPRE:PT_OFF?": "0",
        "WFMOUTPRE:YUNIT?": '"V"',
        "WFMOUTPRE:YMULT?": "0.1",
        "WFMOUTPRE:YOFF?": "10",
        "WFMOUTPRE:YZERO?": "-1",
    }
    values.update(overrides)
    return values


class BinaryScope:
    def __init__(self, samples=(10, 11, 12), *, responses=None):
        self.samples = tuple(samples)
        self.responses = _preamble_responses()
        if responses:
            self.responses.update(responses)
        self.responses.setdefault("CH1:LABEL?", '"Voltage"')
        self.responses.setdefault("CH2:LABEL?", '"Voltage"')
        self.responses.setdefault("CH3:LABEL?", '"Input"')
        self.responses.setdefault("CH4:LABEL?", '"CH4"')
        self.events = []
        self.writes = []
        self.queries = []
        self.binary_calls = []
        self.current_source = "CH1"
        self.read_termination = "\n"

    def write(self, command):
        self.events.append(("write", command))
        self.writes.append(command)
        if command.startswith("DATA:SOURCE "):
            self.current_source = command.split()[-1]

    def query(self, command):
        self.events.append(("query", command))
        self.queries.append(command)
        if command.startswith("SELECT:CH"):
            return self.responses.get(command, "0")
        response = self.responses.get(command)
        if response is None:
            raise AssertionError(f"Unexpected query: {command}")
        return response

    def query_binary_values(self, message, **kwargs):
        self.events.append(("binary", message))
        self.binary_calls.append((message, kwargs))
        container = kwargs["container"]
        return container(self.samples)


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

    with pytest.raises(ValueError, match="Unsupported waveform source"):
        normalize_waveform_source("BUS1")
    with pytest.raises(ValueError, match="Unsupported waveform encoding"):
        normalize_waveform_encoding("JSON")


def test_parse_ascii_curve_accepts_headered_response_and_reports_malformed_data():
    assert parse_ascii_curve(":CURVE 1, 2.5, -3\n") == [1.0, 2.5, -3.0]
    with pytest.raises(DPOWaveformError, match="Malformed ASCII"):
        parse_ascii_curve("CURVE 1,bad,3")


def test_parse_channel_enabled_accepts_verbose_scope_response():
    assert parse_channel_enabled(":SELECT:CH1 1")
    assert parse_channel_enabled("ON")
    assert not parse_channel_enabled(":SELECT:CH2 0")


def test_normalize_channel_label_accepts_verbose_and_empty_responses():
    assert normalize_channel_label(':CH1:LABEL "Input A"', 1) == "Input A"
    assert normalize_channel_label("", 2) == "CH2"


def test_ieee_block_parser_validates_definite_length_payload():
    assert parse_ieee_block_payload(b":CURVE #14abcd\n") == b"abcd"
    with pytest.raises(DPOWaveformError, match="Truncated IEEE waveform block"):
        parse_ieee_block_payload(b"#14ab")
    with pytest.raises(DPOWaveformError, match="Indefinite-length"):
        parse_ieee_block_payload(b"#0abcd")
    with pytest.raises(DPOWaveformError, match="Unexpected non-terminator"):
        parse_ieee_block_payload(b"#14abcdBAD")


def test_binary_decoder_supports_signed_msb_and_unsigned_lsb_words():
    signed = decode_binary_samples(
        struct.pack(">hhh", -1, 0, 32767),
        sample_width=2,
        signed=True,
        byte_order="MSB",
    )
    assert list(signed) == [-1, 0, 32767]

    unsigned = decode_binary_samples(
        struct.pack("<HH", 0, 65535),
        sample_width=2,
        signed=False,
        byte_order="LSB",
    )
    assert list(unsigned) == [0, 65535]


def test_read_waveform_explicitly_sets_range_width_and_binary_encoding_before_curve():
    scope = BinaryScope(samples=(10, 11, 12))

    waveform = read_waveform(
        scope,
        WaveformRequest(source=3, start_index=1, stop_index=3),
    )

    assert scope.writes[:5] == [
        "DATA:SOURCE CH3",
        "DATA:START 1",
        "DATA:STOP 3",
        "DATA:WIDTH 2",
        "DATA:ENCDG RIBINARY",
    ]
    curve_index = scope.events.index(("binary", "CURVE?"))
    assert scope.events.index(("query", "WFMOUTPRE:YZERO?")) < curve_index
    assert scope.events.index(("query", "CH3:LABEL?")) < curve_index

    message, kwargs = scope.binary_calls[0]
    assert message == "CURVE?"
    assert kwargs["datatype"] == "h"
    assert kwargs["is_big_endian"] is True
    assert kwargs["header_fmt"] == "ieee"
    assert kwargs["data_points"] == 3

    assert waveform.source == "CH3"
    assert waveform.label == "Input"
    assert waveform.sample_count == 3
    assert list(waveform.samples) == [10, 11, 12]
    assert list(waveform.iter_times()) == [1.0, 1.5, 2.0]
    assert list(waveform.iter_voltages()) == pytest.approx([-1.0, -0.9, -0.8])


def test_partial_transfer_time_axis_uses_record_index_not_transfer_local_zero():
    scope = BinaryScope(samples=(10, 11))

    waveform = read_waveform(
        scope,
        WaveformRequest(source="CH1", start_index=3, point_count=2),
    )

    assert waveform.start_index == 3
    assert waveform.stop_index == 4
    assert list(waveform.iter_times()) == [2.0, 2.5]


def test_default_stop_is_resolved_from_scope_record_length_and_written_explicitly():
    scope = BinaryScope(samples=(10, 11, 12), responses={"WFMOUTPRE:NR_PT?": "3"})

    waveform = read_waveform(scope, WaveformRequest(source="CH1"))

    assert waveform.stop_index == 3
    assert "DATA:STOP 3" in scope.writes
    # One query resolves the default stop and the second is the coherent preamble read.
    assert scope.queries.count("WFMOUTPRE:NR_PT?") == 2


def test_waveform_point_count_mismatch_is_a_protocol_error():
    scope = BinaryScope(samples=(10, 11))

    with pytest.raises(DPOWaveformError, match="point-count mismatch"):
        read_waveform(
            scope,
            WaveformRequest(source="CH1", start_index=1, stop_index=3),
        )


def test_preamble_must_match_requested_binary_width_and_layout():
    scope = BinaryScope(samples=(10,), responses={"WFMOUTPRE:BYT_NR?": "1"})
    with pytest.raises(DPOWaveformError, match="did not apply requested waveform width"):
        read_waveform(scope, WaveformRequest(source="CH1", stop_index=1, sample_width=2))

    scope = BinaryScope(samples=(10,), responses={"WFMOUTPRE:BYT_OR?": "LSB"})
    with pytest.raises(DPOWaveformError, match="byte order does not match"):
        read_waveform(scope, WaveformRequest(source="CH1", stop_index=1))


def test_envelope_point_format_is_rejected_instead_of_silently_mis_scaling_pairs():
    scope = BinaryScope(samples=(10,), responses={"WFMOUTPRE:PT_FMT?": "ENV"})
    with pytest.raises(DPOWaveformError, match="Envelope/min-max"):
        read_waveform(scope, WaveformRequest(source="CH1", stop_index=1))


def test_ascii_is_explicit_compatibility_path_not_default():
    responses = _preamble_responses(**{"WFMOUTPRE:ENCDG?": "ASC"})
    responses["CH1:LABEL?"] = '"Debug"'
    responses["CURVE?"] = ":CURVE 10,11"
    scope = BinaryScope(samples=(), responses=responses)

    waveform = read_waveform(
        scope,
        WaveformRequest(source="CH1", stop_index=2, encoding="ASCII", sample_width=2),
    )

    assert "DATA:ENCDG ASCII" in scope.writes
    assert not scope.binary_calls
    assert list(waveform.samples) == [10.0, 11.0]


def test_scale_waveform_samples_preserves_legacy_behavior_and_supports_partial_range():
    times, volts = scale_waveform_samples(
        [10, 11, 12],
        x_increment=0.5,
        x_origin=1.0,
        y_multiplier=0.1,
        y_offset=10.0,
        y_zero=-1.0,
    )
    assert times == [1.0, 1.5, 2.0]
    assert volts == pytest.approx([-1.0, -0.9, -0.8])

    times, _ = scale_waveform_samples(
        [10, 11],
        x_increment=0.5,
        x_origin=1.0,
        y_multiplier=1.0,
        y_offset=0.0,
        y_zero=0.0,
        start_index=3,
    )
    assert times == [2.0, 2.5]


def test_legacy_channel_wrapper_returns_lists_over_binary_primary_api():
    scope = BinaryScope(samples=(10, 11), responses={"WFMOUTPRE:NR_PT?": "2"})

    times, volts = read_channel_waveform(scope, 1)

    assert isinstance(times, list)
    assert isinstance(volts, list)
    assert times == [1.0, 1.5]
    assert volts == pytest.approx([-1.0, -0.9])
    assert scope.binary_calls


def test_enabled_channels_queries_all_candidates():
    scope = BinaryScope(
        responses={
            "SELECT:CH1?": "1",
            "SELECT:CH2?": "0",
            "SELECT:CH3?": ":SELECT:CH3 1",
            "SELECT:CH4?": "OFF",
        }
    )
    assert enabled_channels(scope) == [1, 3]


def test_duplicate_labels_remain_distinct_in_legacy_multi_channel_wrapper():
    scope = BinaryScope(
        samples=(10, 11),
        responses={
            "SELECT:CH1?": "1",
            "SELECT:CH2?": "1",
            "SELECT:CH3?": "0",
            "SELECT:CH4?": "0",
            "WFMOUTPRE:NR_PT?": "2",
            "CH1:LABEL?": '"Voltage"',
            "CH2:LABEL?": '"Voltage"',
        },
    )

    times, channel_data = read_enabled_channel_waveforms(scope)

    assert times == [1.0, 1.5]
    assert set(channel_data) == {"CH1 Voltage", "CH2 Voltage"}
    assert len(channel_data) == 2


def test_structured_csv_uses_source_qualified_headers_for_duplicate_labels(tmp_path):
    ch1 = _waveform("CH1", "Voltage", (10, 11))
    ch2 = _waveform("CH2", "Voltage", (12, 13))
    path = tmp_path / "waveforms.csv"

    write_waveforms_csv(path, [ch1, ch2])

    with path.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.reader(csv_file))
    assert rows[0] == ["Time (s)", "CH1 Voltage", "CH2 Voltage"]
    assert len(rows) == 3


def test_alignment_rejects_sample_count_or_x_axis_mismatch():
    reference = _waveform("CH1", "A", (10, 11))
    short = _waveform("CH2", "B", (10,))
    with pytest.raises(DPOWaveformError, match="sample-count mismatch"):
        validate_waveform_alignment([reference, short])

    shifted = _waveform("CH2", "B", (10, 11), x_increment=0.6)
    with pytest.raises(DPOWaveformError, match="X-axis mismatch"):
        validate_waveform_alignment([reference, shifted])


def test_legacy_multi_channel_csv_rejects_mismatched_lengths(tmp_path):
    with pytest.raises(DPOWaveformError, match="expected 2"):
        write_multi_channel_csv(
            tmp_path / "bad.csv",
            [0.0, 1.0],
            {"CH1": [1.0, 2.0], "CH2": [3.0]},
        )
