"""Read an already-configured DPO4054 CURVE? transfer without DATA writes.

Unlike the normal public waveform API, this does not select the source, change
the transfer window/width/encoding, start acquisition or modify scope setup.
Oversized or unsupported preconfigured windows are reported as unavailable,
not silently truncated or reconfigured.
"""
from __future__ import annotations

from array import array
from datetime import datetime, timezone
import math

from .read_only_guard import ReadOnlyVisaSession
from .waveform import (
    WaveformData,
    _read_applied_range,
    _read_binary_curve,
    _read_preamble,
    _read_source_label,
    _validate_preamble,
    normalize_waveform_source,
    parse_ascii_curve,
)
from .io_policy import required_query


class ReadOnlyWaveformUnavailable(RuntimeError):
    """The current setup cannot safely supply a bounded read-only waveform."""


def read_preconfigured_waveform(
    instrument: ReadOnlyVisaSession, *, max_points: int = 1000
) -> WaveformData:
    """Read an existing outgoing waveform, failing closed on unsafe conditions.

    `max_points` is a hard transfer ceiling, NOT a requested configuration.
    To capture larger records, an operator must preconfigure the oscilloscope
    itself and explicitly increase the ceiling for this run.
    """
    if not isinstance(instrument, ReadOnlyVisaSession):
        raise TypeError("Query-only waveform requires a protected VISA session")
    if isinstance(max_points, bool) or not isinstance(max_points, int) or max_points <= 0:
        raise ValueError("max_points must be a positive integer")

    source = normalize_waveform_source(instrument.query("DATA:SOURCE?").strip().strip('"'))
    if source not in {"CH1", "CH2", "CH3", "CH4"}:
        raise ReadOnlyWaveformUnavailable(
            f"Already-selected DATA:SOURCE={source} is not an analog channel; no source write authorized"
        )
    start, stop = _read_applied_range(instrument)
    preamble = _read_preamble(instrument)
    count = preamble.record_point_count
    if count <= 0 or count > stop - start + 1:
        raise ValueError(f"Invalid outgoing waveform count {count} for DATA range {start}..{stop}")
    if count > max_points:
        raise ReadOnlyWaveformUnavailable(
            f"Already-configured waveform contains {count} points, exceeding ceiling {max_points}; "
            "a DATA:STOP write would be necessary to truncate it"
        )
    if preamble.point_format != "Y":
        raise ReadOnlyWaveformUnavailable(
            f"Configured PT_FMT={preamble.point_format!r} is not qualified for read-only samples"
        )
    if not math.isfinite(preamble.x_increment) or preamble.x_increment <= 0:
        raise ValueError("Invalid waveform X increment")
    if not all(math.isfinite(value) for value in (
        preamble.x_zero, preamble.point_offset,
        preamble.y_multiplier, preamble.y_offset, preamble.y_zero,
    )):
        raise ValueError("Non-finite waveform scaling preamble")
    if preamble.encoding.startswith("BIN"):
        if preamble.byte_width not in (1, 2):
            raise ReadOnlyWaveformUnavailable("Only 8/16-bit preconfigured binary samples are supported")
        key = (preamble.binary_format, preamble.byte_order)
        encodings = {
            ("RI", "MSB"): "RIBINARY",
            ("RP", "MSB"): "RPBINARY",
            ("RI", "LSB"): "SRIBINARY",
            ("RP", "LSB"): "SRPBINARY",
        }
        if key not in encodings:
            raise ReadOnlyWaveformUnavailable(f"Unqualified binary format/order: {key!r}")
        encoding = encodings[key]
        _validate_preamble(
            preamble, request_encoding=encoding,
            sample_width=preamble.byte_width, expected_count=count,
        )
        samples = _read_binary_curve(instrument, preamble=preamble, expected_count=count)
    elif preamble.encoding.startswith("ASC"):
        if count > 1_000_000:
            raise ReadOnlyWaveformUnavailable("ASCII transfer exceeds DPO4000 point limit")
        encoding = "ASCII"
        _validate_preamble(
            preamble, request_encoding=encoding,
            sample_width=preamble.byte_width, expected_count=count,
        )
        samples = array("d", parse_ascii_curve(required_query(instrument, "CURVE?")))
    else:
        raise ReadOnlyWaveformUnavailable(
            f"Unqualified preconfigured transfer encoding: {preamble.encoding!r}"
        )
    if len(samples) != count:
        raise ValueError(f"Malformed CURVE? sample count: {len(samples)} received, {count} expected")
    return WaveformData(
        source=source, label=_read_source_label(instrument, source),
        start_index=start, stop_index=start + count - 1,
        requested_encoding=encoding, preamble=preamble, samples=samples,
        acquired_at=datetime.now(timezone.utc),
    )
