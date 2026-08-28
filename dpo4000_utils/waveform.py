"""Deterministic waveform acquisition and CSV export helpers.

The primary waveform API uses explicit DPO4000 transfer state and binary
IEEE-488.2 blocks.  Legacy tuple/list helpers remain as compatibility wrappers,
but large acquisitions should use :class:`WaveformData` directly so timestamps
and scaled voltages can be streamed without allocating duplicate Python lists.
"""

from __future__ import annotations

import csv
import math
import struct
import sys
from array import array
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .connection import temporary_session_attributes
from .control import normalize_scope_response_text
from .errors import DPOError, DPOWaveformError, is_transport_error, transport_exception
from .io_policy import optional_query, required_query


BINARY_ENCODINGS = ("RIBINARY", "RPBINARY", "SRIBINARY", "SRPBINARY")
WAVEFORM_ENCODINGS = (*BINARY_ENCODINGS, "ASCII")
WAVEFORM_SOURCES = (
    "CH1",
    "CH2",
    "CH3",
    "CH4",
    "MATH",
    "REF1",
    "REF2",
    "REF3",
    "REF4",
)
ASCII_MAX_POINTS = 1_000_000

_ENCODING_LAYOUT = {
    "RIBINARY": (True, "MSB"),
    "RPBINARY": (False, "MSB"),
    "SRIBINARY": (True, "LSB"),
    "SRPBINARY": (False, "LSB"),
}


@dataclass(frozen=True)
class WaveformRequest:
    """One explicit waveform transfer request.

    ``start_index`` / ``stop_index`` use the DPO4000 SCPI convention and are
    therefore 1-based and inclusive.  When neither ``stop_index`` nor
    ``point_count`` is supplied, the request transfers from ``start_index`` to
    the end of the waveform record reported by ``WFMOutpre:NR_Pt?``.
    """

    source: str | int
    start_index: int = 1
    stop_index: int | None = None
    point_count: int | None = None
    encoding: str = "RIBINARY"
    sample_width: int = 2


@dataclass(frozen=True)
class WaveformPreamble:
    """Outgoing waveform metadata captured before the CURVE transfer."""

    byte_width: int
    encoding: str
    binary_format: str
    byte_order: str
    record_point_count: int
    point_format: str
    x_unit: str
    x_increment: float
    x_zero: float
    point_offset: float
    y_unit: str
    y_multiplier: float
    y_offset: float
    y_zero: float


@dataclass
class WaveformData:
    """Structured waveform data with compact raw integer samples and metadata.

    ``samples`` keeps the transferred integer data in a standard-library
    :class:`array.array` instead of a Python ``list``.  For a 10-million-point,
    two-byte acquisition this keeps the stored sample payload near 20 MB rather
    than hundreds of megabytes.  Use ``iter_times()`` / ``iter_voltages()`` for
    streaming processing.  ``time_values()`` and ``voltage_values()`` are
    convenience materializers and intentionally allocate 64-bit float arrays.
    """

    source: str
    label: str
    start_index: int
    stop_index: int
    requested_encoding: str
    preamble: WaveformPreamble
    samples: array
    acquired_at: datetime

    @property
    def sample_count(self) -> int:
        return len(self.samples)

    @property
    def display_name(self) -> str:
        label = self.label.strip()
        if not label or label.upper() == self.source.upper():
            return self.source
        return f"{self.source} {label}"

    def _validate_index(self, index: int) -> int:
        value = int(index)
        if value < 0 or value >= self.sample_count:
            raise IndexError(f"Waveform sample index {value} is out of range.")
        return value

    def time_at(self, index: int) -> float:
        """Return the absolute X coordinate for one transferred point."""
        value = self._validate_index(index)
        record_index = (self.start_index - 1) + value
        return self.preamble.x_zero + self.preamble.x_increment * (
            record_index - self.preamble.point_offset
        )

    def voltage_at(self, index: int) -> float:
        """Return one raw sample converted to the preamble Y units."""
        value = self._validate_index(index)
        raw = self.samples[value]
        return (
            (raw - self.preamble.y_offset) * self.preamble.y_multiplier
            + self.preamble.y_zero
        )

    def iter_times(self) -> Iterator[float]:
        for index in range(self.sample_count):
            yield self.time_at(index)

    def iter_voltages(self) -> Iterator[float]:
        for raw in self.samples:
            yield (
                (raw - self.preamble.y_offset) * self.preamble.y_multiplier
                + self.preamble.y_zero
            )

    def time_values(self) -> array:
        """Materialize all X coordinates as an ``array('d')``."""
        return array("d", self.iter_times())

    def voltage_values(self) -> array:
        """Materialize all scaled Y values as an ``array('d')``."""
        return array("d", self.iter_voltages())


def validate_channel(channel: int | str) -> int:
    """Return a valid DPO4000 analog channel number."""
    if isinstance(channel, bool):
        raise ValueError("Channel must be between 1 and 4.")
    try:
        channel_number = int(channel)
    except (TypeError, ValueError) as exc:
        raise ValueError("Channel must be between 1 and 4.") from exc
    if channel_number < 1 or channel_number > 4:
        raise ValueError("Channel must be between 1 and 4.")
    return channel_number


def normalize_waveform_source(source: str | int) -> str:
    """Normalize a supported analog/MATH/reference waveform source."""
    if isinstance(source, bool):
        raise ValueError("Waveform source must be CH1..CH4, MATH, or REF1..REF4.")
    if isinstance(source, int):
        return f"CH{validate_channel(source)}"

    token = str(source or "").strip().upper().replace(" ", "")
    if token.isdigit():
        token = f"CH{validate_channel(token)}"
    if token == "MATH1":
        token = "MATH"
    if token not in WAVEFORM_SOURCES:
        raise ValueError(
            f"Unsupported waveform source {source!r}; expected CH1..CH4, MATH, or REF1..REF4."
        )
    return token


def normalize_waveform_encoding(encoding: str) -> str:
    token = str(encoding or "").strip().upper().replace("_", "")
    aliases = {
        "RI": "RIBINARY",
        "RP": "RPBINARY",
        "SRI": "SRIBINARY",
        "SRP": "SRPBINARY",
        "ASC": "ASCII",
    }
    token = aliases.get(token, token)
    if token not in WAVEFORM_ENCODINGS:
        raise ValueError(
            f"Unsupported waveform encoding {encoding!r}; expected one of {WAVEFORM_ENCODINGS}."
        )
    return token


def normalize_sample_width(width: int | str) -> int:
    if isinstance(width, bool):
        raise ValueError("Waveform sample width must be 1 or 2 bytes.")
    try:
        value = int(width)
    except (TypeError, ValueError) as exc:
        raise ValueError("Waveform sample width must be 1 or 2 bytes.") from exc
    if value not in (1, 2):
        raise ValueError("Waveform sample width must be 1 or 2 bytes.")
    return value


def _positive_index(value: int | str, *, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a positive integer.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive integer.") from exc
    if number <= 0:
        raise ValueError(f"{field} must be a positive integer.")
    return number


def _write_required(scope: Any, command: str) -> None:
    try:
        scope.write(command)
    except DPOError:
        raise
    except Exception as exc:
        if is_transport_error(exc):
            raise transport_exception(exc, f"Writing waveform command {command!r}") from exc
        raise


def _query_value(scope: Any, command: str) -> str:
    return required_query(scope, command, normalizer=normalize_scope_response_text)


def _query_int(scope: Any, command: str, *, field: str) -> int:
    text = _query_value(scope, command)
    try:
        value = int(float(text))
    except (TypeError, ValueError) as exc:
        raise DPOWaveformError(f"Invalid {field} returned by {command}: {text!r}.") from exc
    return value


def _query_float(scope: Any, command: str, *, field: str) -> float:
    text = _query_value(scope, command)
    try:
        value = float(text)
    except (TypeError, ValueError) as exc:
        raise DPOWaveformError(f"Invalid {field} returned by {command}: {text!r}.") from exc
    if not math.isfinite(value):
        raise DPOWaveformError(f"Non-finite {field} returned by {command}: {text!r}.")
    return value


def _read_preamble(scope: Any) -> WaveformPreamble:
    """Read one coherent outgoing preamble after DATA transfer configuration."""
    return WaveformPreamble(
        byte_width=_query_int(scope, "WFMOUTPRE:BYT_NR?", field="waveform byte width"),
        encoding=_query_value(scope, "WFMOUTPRE:ENCDG?").upper(),
        binary_format=_query_value(scope, "WFMOUTPRE:BN_FMT?").upper(),
        byte_order=_query_value(scope, "WFMOUTPRE:BYT_OR?").upper(),
        record_point_count=_query_int(
            scope, "WFMOUTPRE:NR_PT?", field="waveform record point count"
        ),
        point_format=_query_value(scope, "WFMOUTPRE:PT_FMT?").upper(),
        x_unit=_query_value(scope, "WFMOUTPRE:XUNIT?"),
        x_increment=_query_float(scope, "WFMOUTPRE:XINCR?", field="X increment"),
        x_zero=_query_float(scope, "WFMOUTPRE:XZERO?", field="X zero"),
        point_offset=_query_float(scope, "WFMOUTPRE:PT_OFF?", field="point offset"),
        y_unit=_query_value(scope, "WFMOUTPRE:YUNIT?"),
        y_multiplier=_query_float(scope, "WFMOUTPRE:YMULT?", field="Y multiplier"),
        y_offset=_query_float(scope, "WFMOUTPRE:YOFF?", field="Y offset"),
        y_zero=_query_float(scope, "WFMOUTPRE:YZERO?", field="Y zero"),
    )


def _validate_preamble(
    preamble: WaveformPreamble,
    *,
    request_encoding: str,
    sample_width: int,
    start_index: int,
    stop_index: int,
) -> None:
    if preamble.byte_width != sample_width:
        raise DPOWaveformError(
            "Scope did not apply requested waveform width: "
            f"requested {sample_width}, preamble reports {preamble.byte_width}."
        )
    if preamble.record_point_count <= 0:
        raise DPOWaveformError(
            f"Scope reported invalid waveform record length {preamble.record_point_count}."
        )
    if stop_index > preamble.record_point_count:
        raise DPOWaveformError(
            f"Requested DATA:STOP {stop_index} exceeds waveform record length "
            f"{preamble.record_point_count}."
        )
    if preamble.point_format != "Y":
        raise DPOWaveformError(
            "Envelope/min-max waveform point format is not silently flattened by the v0.6 API. "
            f"Scope reported PT_FMT={preamble.point_format!r}; use SAMPLE/HIRES/AVERAGE "
            "or add an explicit envelope-processing policy."
        )
    if preamble.x_increment <= 0:
        raise DPOWaveformError(
            f"Scope reported invalid X increment {preamble.x_increment!r}."
        )

    if request_encoding == "ASCII":
        if not preamble.encoding.startswith("ASC"):
            raise DPOWaveformError(
                f"Scope preamble encoding {preamble.encoding!r} does not match ASCII request."
            )
        return

    if not preamble.encoding.startswith("BIN"):
        raise DPOWaveformError(
            f"Scope preamble encoding {preamble.encoding!r} is not binary after "
            f"requesting {request_encoding}."
        )
    signed, expected_order = _ENCODING_LAYOUT[request_encoding]
    expected_format = "RI" if signed else "RP"
    if preamble.binary_format != expected_format:
        raise DPOWaveformError(
            "Scope binary format does not match request: "
            f"expected {expected_format}, got {preamble.binary_format!r}."
        )
    if sample_width > 1 and preamble.byte_order != expected_order:
        raise DPOWaveformError(
            "Scope byte order does not match request: "
            f"expected {expected_order}, got {preamble.byte_order!r}."
        )


def parse_ascii_curve(raw_data: str) -> list[float]:
    """Parse an explicit compatibility/debug ASCII ``CURVE?`` response."""
    text = str(raw_data or "").strip()
    upper = text.upper()
    if upper.startswith(":CURVE") or upper.startswith("CURVE"):
        parts = text.split(None, 1)
        text = parts[1] if len(parts) == 2 else ""
    try:
        return [float(value) for value in text.split(",") if value.strip()]
    except ValueError as exc:
        raise DPOWaveformError(f"Malformed ASCII CURVE response: {raw_data!r}.") from exc


def parse_ieee_block_payload(raw_data: bytes) -> bytes:
    """Extract and strictly validate one IEEE-488.2 definite-length block."""
    raw = bytes(raw_data)
    marker = raw.find(b"#")
    if marker < 0:
        raise DPOWaveformError("Binary CURVE response does not contain an IEEE block header.")
    if len(raw) < marker + 2:
        raise DPOWaveformError("Truncated IEEE block header in binary CURVE response.")
    digit_byte = raw[marker + 1 : marker + 2]
    if not digit_byte.isdigit():
        raise DPOWaveformError("Invalid IEEE block length-digit field in CURVE response.")
    digit_count = int(digit_byte)
    if digit_count <= 0:
        raise DPOWaveformError("Indefinite-length IEEE blocks are not supported for CURVE data.")
    length_start = marker + 2
    length_end = length_start + digit_count
    if len(raw) < length_end:
        raise DPOWaveformError("Truncated IEEE block byte-count field in CURVE response.")
    length_text = raw[length_start:length_end]
    if not length_text.isdigit():
        raise DPOWaveformError("Invalid IEEE block byte-count field in CURVE response.")
    payload_length = int(length_text)
    payload_end = length_end + payload_length
    if len(raw) < payload_end:
        raise DPOWaveformError(
            f"Truncated IEEE waveform block: declared {payload_length} payload bytes, "
            f"received {max(0, len(raw) - length_end)}."
        )
    trailing = raw[payload_end:]
    if trailing.strip(b"\r\n \t"):
        raise DPOWaveformError("Unexpected non-terminator bytes follow the IEEE waveform block.")
    return raw[length_end:payload_end]


def decode_binary_samples(
    payload: bytes,
    *,
    sample_width: int,
    signed: bool,
    byte_order: str,
) -> array:
    """Decode compact one/two-byte DPO4000 integer waveform samples."""
    width = normalize_sample_width(sample_width)
    order = str(byte_order or "").strip().upper()
    if order not in {"MSB", "LSB"}:
        raise DPOWaveformError(f"Unsupported waveform byte order {byte_order!r}.")
    if len(payload) % width:
        raise DPOWaveformError(
            f"Binary waveform payload length {len(payload)} is not divisible by width {width}."
        )

    if width == 1:
        values = array("b" if signed else "B")
        values.frombytes(payload)
        return values

    values = array("h" if signed else "H")
    if values.itemsize != 2:  # pragma: no cover - CPython supported platforms use 2-byte h/H.
        raise DPOWaveformError("Host array('h') is not two bytes; cannot decode DPO waveform.")
    values.frombytes(payload)
    source_is_big_endian = order == "MSB"
    host_is_big_endian = sys.byteorder == "big"
    if source_is_big_endian != host_is_big_endian:
        values.byteswap()
    return values


def _pyvisa_array_container(typecode: str):
    """Return a PyVISA binary container factory backed by ``array.array``."""

    def build(values: Iterable[Any]) -> array:
        result = array(typecode)
        result.extend(
            value[0] if isinstance(value, tuple) and len(value) == 1 else value
            for value in values
        )
        return result

    return build


def _read_binary_curve(
    scope: Any,
    *,
    preamble: WaveformPreamble,
    expected_count: int,
) -> array:
    signed = preamble.binary_format == "RI"
    typecode = (
        "b"
        if preamble.byte_width == 1 and signed
        else "B"
        if preamble.byte_width == 1
        else "h"
        if signed
        else "H"
    )
    datatype = typecode
    query_binary_values = getattr(scope, "query_binary_values", None)

    if callable(query_binary_values):
        try:
            values = query_binary_values(
                "CURVE?",
                datatype=datatype,
                is_big_endian=preamble.byte_order == "MSB",
                container=_pyvisa_array_container(typecode),
                header_fmt="ieee",
                expect_termination=True,
                data_points=expected_count,
            )
        except DPOError:
            raise
        except (ValueError, TypeError, struct.error) as exc:
            raise DPOWaveformError(f"Malformed binary CURVE block: {exc}") from exc
        except Exception as exc:
            if is_transport_error(exc):
                raise transport_exception(exc, "Reading binary waveform CURVE block") from exc
            raise
        if not isinstance(values, array):
            try:
                values = array(typecode, values)
            except Exception as exc:
                raise DPOWaveformError(
                    f"Binary CURVE decoder returned unsupported sample container {type(values)!r}."
                ) from exc
        return values

    # Lightweight/custom VISA-like backends may not expose query_binary_values.
    # Keep a strict raw-block fallback for tests and compatibility.
    _write_required(scope, "CURVE?")
    read_raw = getattr(scope, "read_raw", None)
    if not callable(read_raw):
        raise DPOWaveformError(
            "Binary waveform acquisition requires query_binary_values() or read_raw()."
        )
    try:
        with temporary_session_attributes(scope, read_termination=None):
            raw = read_raw()
    except DPOError:
        raise
    except Exception as exc:
        if is_transport_error(exc):
            raise transport_exception(exc, "Reading raw binary waveform CURVE block") from exc
        raise
    payload = parse_ieee_block_payload(raw)
    return decode_binary_samples(
        payload,
        sample_width=preamble.byte_width,
        signed=signed,
        byte_order=preamble.byte_order,
    )


def _read_source_label(scope: Any, source: str) -> str:
    if source.startswith("CH"):
        command = f"{source}:LABEL?"
    elif source.startswith("REF"):
        command = f"{source}:LABEL?"
    else:
        return source
    label = optional_query(scope, command, normalizer=normalize_scope_response_text)
    return label.strip() or source


def _resolve_transfer_range(
    scope: Any,
    request: WaveformRequest,
    *,
    source: str,
) -> tuple[int, int]:
    start = _positive_index(request.start_index, field="Waveform start index")
    if request.stop_index is not None and request.point_count is not None:
        raise ValueError("Specify either stop_index or point_count, not both.")

    if request.stop_index is not None:
        stop = _positive_index(request.stop_index, field="Waveform stop index")
    elif request.point_count is not None:
        count = _positive_index(request.point_count, field="Waveform point count")
        stop = start + count - 1
    else:
        record_points = _query_int(
            scope,
            "WFMOUTPRE:NR_PT?",
            field=f"{source} waveform record point count",
        )
        stop = record_points

    if stop < start:
        raise ValueError("Waveform stop index must be greater than or equal to start index.")
    return start, stop


def read_waveform(scope: Any, request: WaveformRequest) -> WaveformData:
    """Read one deterministic waveform according to ``request``.

    The transfer sequence follows the DPO4000 programmer manual: source and
    transfer format/range are explicitly selected, ``WFMOutpre`` metadata is read
    before the data transfer, and binary CURVE data uses an IEEE-488.2 block.
    """
    source = normalize_waveform_source(request.source)
    encoding = normalize_waveform_encoding(request.encoding)
    sample_width = normalize_sample_width(request.sample_width)

    _write_required(scope, f"DATA:SOURCE {source}")
    start, stop = _resolve_transfer_range(scope, request, source=source)
    _write_required(scope, f"DATA:START {start}")
    _write_required(scope, f"DATA:STOP {stop}")
    _write_required(scope, f"DATA:WIDTH {sample_width}")
    _write_required(scope, f"DATA:ENCDG {encoding}")

    preamble = _read_preamble(scope)
    _validate_preamble(
        preamble,
        request_encoding=encoding,
        sample_width=sample_width,
        start_index=start,
        stop_index=stop,
    )
    label = _read_source_label(scope, source)
    expected_count = stop - start + 1

    if encoding == "ASCII":
        if expected_count > ASCII_MAX_POINTS:
            raise DPOWaveformError(
                "ASCII CURVE transfers above 1,000,000 points are not supported by the "
                "DPO4000 family; use the default binary encoding."
            )
        raw_text = required_query(scope, "CURVE?")
        parsed = parse_ascii_curve(raw_text)
        samples = array("d", parsed)
    else:
        samples = _read_binary_curve(
            scope,
            preamble=preamble,
            expected_count=expected_count,
        )

    if len(samples) != expected_count:
        raise DPOWaveformError(
            "Waveform point-count mismatch: "
            f"requested {expected_count} points ({start}..{stop}), received {len(samples)}."
        )

    return WaveformData(
        source=source,
        label=label,
        start_index=start,
        stop_index=stop,
        requested_encoding=encoding,
        preamble=preamble,
        samples=samples,
        acquired_at=datetime.now(timezone.utc),
    )


def read_channel_waveform_data(
    scope: Any,
    channel: int | str,
    *,
    start_index: int = 1,
    stop_index: int | None = None,
    point_count: int | None = None,
    encoding: str = "RIBINARY",
    sample_width: int = 2,
) -> WaveformData:
    """Read one analog channel and return structured waveform data."""
    return read_waveform(
        scope,
        WaveformRequest(
            source=validate_channel(channel),
            start_index=start_index,
            stop_index=stop_index,
            point_count=point_count,
            encoding=encoding,
            sample_width=sample_width,
        ),
    )


def parse_channel_enabled(response: str) -> bool:
    """Return whether a ``SELECT:CHn?`` response means the channel is enabled."""
    parts = str(response or "").strip().upper().split()
    token = parts[-1] if parts else ""
    return token in {"1", "ON", "TRUE"}


def normalize_channel_label(response: str, channel: int) -> str:
    """Return a normalized label with a CHn fallback."""
    text = str(response or "").strip()
    if '"' in text:
        label = text.split('"', 1)[1].rsplit('"', 1)[0]
    else:
        prefix = f":CH{validate_channel(channel)}:LABEL"
        label = text.replace(prefix, "").strip()
    return label or f"CH{validate_channel(channel)}"


def scale_waveform_samples(
    raw_samples: Sequence[float],
    *,
    x_increment: float,
    x_origin: float,
    y_multiplier: float,
    y_offset: float,
    y_zero: float,
    start_index: int = 1,
    point_offset: float = 0.0,
) -> tuple[list[float], list[float]]:
    """Compatibility helper that scales explicit raw samples into Python lists."""
    start = _positive_index(start_index, field="Waveform start index")
    times = [
        x_origin + ((start - 1 + index) - point_offset) * x_increment
        for index in range(len(raw_samples))
    ]
    voltages = [(sample - y_offset) * y_multiplier + y_zero for sample in raw_samples]
    return times, voltages


def read_channel_waveform(scope: Any, channel: int) -> tuple[list[float], list[float]]:
    """Legacy tuple/list wrapper over the binary structured acquisition API."""
    waveform = read_channel_waveform_data(scope, channel)
    return list(waveform.iter_times()), list(waveform.iter_voltages())


def enabled_channels(scope: Any, channels: Iterable[int] = range(1, 5)) -> list[int]:
    """Return enabled channel numbers from ``SELECT:CHn?`` queries."""
    result: list[int] = []
    for channel in channels:
        channel = validate_channel(channel)
        response = required_query(scope, f"SELECT:CH{channel}?")
        if parse_channel_enabled(response):
            result.append(channel)
    return result


def _float_equal(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-15)


def validate_waveform_alignment(waveforms: Sequence[WaveformData]) -> None:
    """Require one common X axis before a combined multi-channel export."""
    if not waveforms:
        raise DPOWaveformError("No enabled channels found.")
    reference = waveforms[0]
    for waveform in waveforms[1:]:
        if waveform.sample_count != reference.sample_count:
            raise DPOWaveformError(
                f"Waveform sample-count mismatch: {reference.source} has "
                f"{reference.sample_count}, {waveform.source} has {waveform.sample_count}."
            )
        if waveform.start_index != reference.start_index or waveform.stop_index != reference.stop_index:
            raise DPOWaveformError(
                f"Waveform transfer-range mismatch between {reference.source} and {waveform.source}."
            )
        for field in ("x_increment", "x_zero", "point_offset"):
            left = getattr(reference.preamble, field)
            right = getattr(waveform.preamble, field)
            if not _float_equal(left, right):
                raise DPOWaveformError(
                    f"Waveform X-axis mismatch for {field}: {reference.source}={left!r}, "
                    f"{waveform.source}={right!r}."
                )
        if waveform.preamble.x_unit != reference.preamble.x_unit:
            raise DPOWaveformError(
                f"Waveform X-unit mismatch: {reference.source}={reference.preamble.x_unit!r}, "
                f"{waveform.source}={waveform.preamble.x_unit!r}."
            )


def read_enabled_waveforms(
    scope: Any,
    channels: Iterable[int] = range(1, 5),
    *,
    start_index: int = 1,
    stop_index: int | None = None,
    point_count: int | None = None,
    encoding: str = "RIBINARY",
    sample_width: int = 2,
) -> dict[str, WaveformData]:
    """Read all enabled analog channels keyed by immutable source identity."""
    result: dict[str, WaveformData] = {}
    for channel in enabled_channels(scope, channels):
        waveform = read_channel_waveform_data(
            scope,
            channel,
            start_index=start_index,
            stop_index=stop_index,
            point_count=point_count,
            encoding=encoding,
            sample_width=sample_width,
        )
        result[waveform.source] = waveform
    values = list(result.values())
    validate_waveform_alignment(values)
    return result


def read_enabled_channel_waveforms(
    scope: Any,
    channels: Iterable[int] = range(1, 5),
) -> tuple[list[float], dict[str, list[float]]]:
    """Legacy multi-channel wrapper with source-qualified, collision-free keys."""
    waveforms = read_enabled_waveforms(scope, channels)
    values = list(waveforms.values())
    first = values[0]
    return (
        list(first.iter_times()),
        {waveform.display_name: list(waveform.iter_voltages()) for waveform in values},
    )


def write_single_channel_csv(
    path: str | Path,
    times: Sequence[float],
    voltages: Sequence[float],
) -> Path:
    """Write legacy time/voltage sequences after validating equal length."""
    if len(times) != len(voltages):
        raise DPOWaveformError(
            f"Cannot write CSV: {len(times)} time values but {len(voltages)} voltage values."
        )
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["Time (s)", "Voltage (V)"])
        writer.writerows(zip(times, voltages))
    return output_path


def write_multi_channel_csv(
    path: str | Path,
    times: Sequence[float],
    channel_data: Mapping[str, Sequence[float]],
) -> Path:
    """Write legacy multi-channel sequences with strict point-count validation."""
    if not channel_data:
        raise DPOWaveformError("No enabled channels found.")
    expected = len(times)
    for name, values in channel_data.items():
        if len(values) != expected:
            raise DPOWaveformError(
                f"Cannot write aligned CSV: {name} has {len(values)} points, expected {expected}."
            )

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    channel_names = list(channel_data.keys())
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["Time (s)", *channel_names])
        for index, time_value in enumerate(times):
            writer.writerow([time_value, *[channel_data[name][index] for name in channel_names]])
    return output_path


def write_waveform_csv(path: str | Path, waveform: WaveformData) -> Path:
    """Stream one structured waveform to CSV without materializing time/voltage lists."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    x_unit = waveform.preamble.x_unit or "s"
    y_unit = waveform.preamble.y_unit or "V"
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([f"Time ({x_unit})", f"{waveform.display_name} ({y_unit})"])
        for index in range(waveform.sample_count):
            writer.writerow([waveform.time_at(index), waveform.voltage_at(index)])
    return output_path


def write_waveforms_csv(
    path: str | Path,
    waveforms: Mapping[str, WaveformData] | Sequence[WaveformData],
) -> Path:
    """Stream aligned structured waveforms to one collision-free CSV file."""
    values = list(waveforms.values()) if isinstance(waveforms, Mapping) else list(waveforms)
    validate_waveform_alignment(values)
    sources = [waveform.source for waveform in values]
    if len(set(sources)) != len(sources):
        raise DPOWaveformError("Combined waveform export contains duplicate source identities.")

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    x_unit = values[0].preamble.x_unit or "s"
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([f"Time ({x_unit})", *[waveform.display_name for waveform in values]])
        for index in range(values[0].sample_count):
            writer.writerow(
                [values[0].time_at(index), *[waveform.voltage_at(index) for waveform in values]]
            )
    return output_path


def save_channel_waveform_csv(scope: Any, channel: int, filename: str | Path) -> Path:
    """Acquire one channel with binary transfer and stream it to CSV."""
    waveform = read_channel_waveform_data(scope, channel)
    return write_waveform_csv(filename, waveform)


def save_enabled_channels_to_single_csv(scope: Any, filename: str | Path) -> Path:
    """Acquire enabled channels and stream one strictly aligned CSV."""
    return write_waveforms_csv(filename, read_enabled_waveforms(scope))


def save_enabled_channels_to_separate_csv(scope: Any, base_filename: str | Path) -> list[Path]:
    """Acquire enabled channels once and stream one CSV file per source."""
    base_path = Path(base_filename)
    waveforms = read_enabled_waveforms(scope)
    written: list[Path] = []
    for waveform in waveforms.values():
        output_path = base_path.with_name(f"{base_path.name}_{waveform.source}.csv")
        written.append(write_waveform_csv(output_path, waveform))
    return written


class WaveformMixin:
    """Public structured waveform acquisition and CSV export API."""

    def read_waveform(self, request: WaveformRequest) -> WaveformData:
        return read_waveform(self.ensure_connected(), request)

    def read_channel_waveform_data(
        self,
        channel: int | str,
        *,
        start_index: int = 1,
        stop_index: int | None = None,
        point_count: int | None = None,
        encoding: str = "RIBINARY",
        sample_width: int = 2,
    ) -> WaveformData:
        return read_channel_waveform_data(
            self.ensure_connected(),
            channel,
            start_index=start_index,
            stop_index=stop_index,
            point_count=point_count,
            encoding=encoding,
            sample_width=sample_width,
        )

    def read_enabled_waveforms(self, **kwargs: Any) -> dict[str, WaveformData]:
        return read_enabled_waveforms(self.ensure_connected(), **kwargs)

    def _read_channel_waveform(self, channel: int):
        """Backward-compatible tuple/list acquisition wrapper."""
        return read_channel_waveform(self.ensure_connected(), channel)

    def save_waveform_to_csv(self, channel, filename):
        return save_channel_waveform_csv(self.ensure_connected(), channel, filename)

    def save_all_channels_to_csv(self, base_filename):
        return save_enabled_channels_to_separate_csv(self.ensure_connected(), base_filename)

    def save_all_channels_to_single_csv(self, filename):
        return save_enabled_channels_to_single_csv(self.ensure_connected(), filename)


__all__ = [
    "ASCII_MAX_POINTS",
    "BINARY_ENCODINGS",
    "WAVEFORM_ENCODINGS",
    "WAVEFORM_SOURCES",
    "WaveformData",
    "WaveformMixin",
    "WaveformPreamble",
    "WaveformRequest",
    "decode_binary_samples",
    "enabled_channels",
    "normalize_channel_label",
    "normalize_sample_width",
    "normalize_waveform_encoding",
    "normalize_waveform_source",
    "parse_ascii_curve",
    "parse_channel_enabled",
    "parse_ieee_block_payload",
    "read_channel_waveform",
    "read_channel_waveform_data",
    "read_enabled_channel_waveforms",
    "read_enabled_waveforms",
    "read_waveform",
    "save_channel_waveform_csv",
    "save_enabled_channels_to_separate_csv",
    "save_enabled_channels_to_single_csv",
    "scale_waveform_samples",
    "validate_channel",
    "validate_waveform_alignment",
    "write_multi_channel_csv",
    "write_single_channel_csv",
    "write_waveform_csv",
    "write_waveforms_csv",
]
