"""Screen hardcopy capture helpers."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from .connection import temporary_session_attributes
from .errors import (
    DPOError,
    DPOImageCaptureError,
    add_exception_note,
    is_transport_error,
    transport_exception,
)


logger = logging.getLogger(__name__)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_IEND = b"IEND\xaeB`\x82"
_MAX_HARDCOPY_BYTES = 64 * 1024 * 1024
_MAX_HARDCOPY_PREFIX_BYTES = 4096


class HardcopyCaptureError(DPOImageCaptureError):
    """Backward-compatible image-capture exception name."""


def strip_ieee_block_header(payload: bytes) -> bytes:
    """Strip an IEEE 488.2 definite-length block header if one is present."""
    if not payload.startswith(b"#") or len(payload) < 2:
        return payload

    try:
        digit_count = int(payload[1:2])
    except ValueError:
        return payload

    if digit_count <= 0:
        return payload

    header_end = 2 + digit_count
    if len(payload) < header_end:
        return payload

    try:
        data_length = int(payload[2:header_end])
    except ValueError:
        return payload

    data_end = header_end + data_length
    if len(payload) >= data_end:
        return payload[header_end:data_end]

    return payload[header_end:]


def trim_png_after_iend(payload: bytes) -> bytes:
    """Trim bytes after the PNG IEND chunk."""
    iend = payload.find(PNG_IEND)
    if iend >= 0:
        return payload[: iend + len(PNG_IEND)]
    return payload


def extract_png_bytes(payload: bytes) -> bytes:
    """Extract a clean PNG stream from Tektronix hardcopy response bytes."""
    payload = strip_ieee_block_header(bytes(payload))
    start = payload.find(PNG_SIGNATURE)
    if start < 0:
        return payload
    return trim_png_after_iend(payload[start:])


def hardcopy_response_prefix(payload: bytes, limit: int = 120) -> str:
    """Return a readable response prefix for error messages."""
    prefix = bytes(payload)[:limit].replace(b"\r", b"\\r").replace(b"\n", b"\\n")
    try:
        return prefix.decode("ascii", errors="replace")
    except Exception:
        return repr(prefix)


def require_png_bytes(payload: bytes) -> bytes:
    """Extract PNG bytes and raise a diagnostic error if no PNG is present."""
    if not payload:
        raise HardcopyCaptureError("Scope returned empty image data.")

    png = extract_png_bytes(payload)
    if not png.startswith(PNG_SIGNATURE):
        raise HardcopyCaptureError(
            "No PNG signature found in scope hardcopy response. "
            f"First bytes: {hardcopy_response_prefix(payload)!r}. "
            "Try USB/VXI-11 first; for raw SOCKET check port and VISA backend."
        )
    return png


def _normalize_format_response(response: str) -> str:
    """Extract a safe HARDCOPY:FORMAT token from verbose or terse readback."""
    text = str(response or "").strip().strip(";")
    if not text:
        return ""
    token = text.split()[-1].strip('"').upper()
    if any(separator in token for separator in (";", "\r", "\n")):
        return ""
    return token


def _read_hardcopy_format(instrument: Any) -> str:
    query = getattr(instrument, "query", None)
    if not callable(query):
        return ""
    try:
        return _normalize_format_response(query("HARDCOPY:FORMAT?"))
    except Exception as exc:
        # Some lightweight/fake backends do not expose query(). Capture can still
        # proceed; real transport loss will normally fail on the following write.
        logger.debug("Could not read HARDCOPY:FORMAT before capture: %s", exc)
        return ""


def _read_exact_bytes(instrument: Any, count: int) -> bytes:
    """Read exactly *count* bytes without waiting for a VISA message-end marker."""
    if count < 0:
        raise HardcopyCaptureError("Negative hardcopy byte count is invalid.")
    if count == 0:
        return b""

    read_bytes = getattr(instrument, "read_bytes", None)
    if not callable(read_bytes):
        raise AttributeError("Instrument does not expose read_bytes().")

    data = bytes(read_bytes(count, break_on_termchar=False))
    if len(data) != count:
        raise HardcopyCaptureError(
            f"Short hardcopy read: expected {count} bytes, received {len(data)}."
        )
    return data


def _read_png_chunks(instrument: Any, prefix: bytes = b"") -> bytes:
    """Read one PNG by its chunk lengths and stop immediately after IEND."""
    buffered = bytearray(prefix)

    if not buffered:
        buffered.extend(_read_exact_bytes(instrument, 1))

    if buffered[:1] != b"#" and len(buffered) < len(PNG_SIGNATURE):
        buffered.extend(
            _read_exact_bytes(instrument, len(PNG_SIGNATURE) - len(buffered))
        )

    while PNG_SIGNATURE not in buffered:
        if len(buffered) >= _MAX_HARDCOPY_PREFIX_BYTES:
            raise HardcopyCaptureError(
                "No PNG signature found within the hardcopy response prefix. "
                f"First bytes: {hardcopy_response_prefix(buffered)!r}."
            )
        buffered.extend(_read_exact_bytes(instrument, 1))

    start = buffered.find(PNG_SIGNATURE)
    png = bytearray(buffered[start:])
    if len(png) != len(PNG_SIGNATURE):
        # Prefix scanning reads only through the signature. Keep this guard so a
        # future caller cannot accidentally feed unparsed PNG payload bytes here.
        raise HardcopyCaptureError("Unexpected buffered bytes after PNG signature.")

    while True:
        header = _read_exact_bytes(instrument, 8)
        chunk_length = int.from_bytes(header[:4], byteorder="big", signed=False)
        chunk_type = header[4:8]
        if chunk_length > _MAX_HARDCOPY_BYTES:
            raise HardcopyCaptureError(
                f"Unreasonable PNG chunk length {chunk_length} for {chunk_type!r}."
            )

        tail = _read_exact_bytes(instrument, chunk_length + 4)
        png.extend(header)
        png.extend(tail)
        if len(png) > _MAX_HARDCOPY_BYTES:
            raise HardcopyCaptureError(
                f"Hardcopy PNG exceeded {_MAX_HARDCOPY_BYTES} bytes."
            )
        if chunk_type == b"IEND":
            return bytes(png)


def _read_hardcopy_payload(instrument: Any) -> bytes:
    """Read hardcopy bytes without depending on a prompt VISA EOM indication.

    PyVISA ``read_raw()`` waits for the backend to report end-of-message. Some
    DPO4054/VXI-11 combinations return a complete PNG but do not terminate the
    message promptly, making a valid capture take the full VISA timeout. When
    ``read_bytes()`` is available, use explicit framing instead: consume a
    definite-length IEEE block exactly, or parse the PNG chunk lengths until
    IEND. Lightweight/non-PyVISA fakes retain the legacy ``read_raw()`` path.
    """
    read_bytes = getattr(instrument, "read_bytes", None)
    if not callable(read_bytes):
        return bytes(instrument.read_raw())

    first = _read_exact_bytes(instrument, 1)
    if first != b"#":
        return _read_png_chunks(instrument, first)

    digit = _read_exact_bytes(instrument, 1)
    if digit in b"123456789":
        digit_count = int(digit)
        length_text = _read_exact_bytes(instrument, digit_count)
        if not length_text.isdigit():
            raise HardcopyCaptureError(
                f"Malformed IEEE hardcopy length field: {length_text!r}."
            )
        data_length = int(length_text)
        if data_length <= 0 or data_length > _MAX_HARDCOPY_BYTES:
            raise HardcopyCaptureError(
                f"Invalid IEEE hardcopy payload length: {data_length}."
            )
        return _read_exact_bytes(instrument, data_length)

    # ``#0`` is an indefinite block. Malformed framing is handled the same way:
    # scan forward to the PNG signature, then let PNG chunk lengths define EOM.
    return _read_png_chunks(instrument, first + digit)


def capture_screen_png(
    instrument: Any,
    *,
    timeout_ms: int = 60_000,
    command_delay_s: float = 0.03,
) -> bytes:
    """Capture the oscilloscope display and return validated PNG bytes.

    Only the hardcopy format is changed at instrument level. Unlike the legacy
    path this does not issue ``*CLS``, does not alter HEADER/VERBOSE, and does not
    modify SAVE:IMAGE settings. The previous HARDCOPY:FORMAT is restored when it
    can be read back. VISA timeout/termination settings are restored exactly.

    On PyVISA-like sessions, hardcopy reads are length-driven and stop as soon as
    the complete PNG has been received. This avoids waiting for an unreliable
    VXI-11 message-end indication after the PNG IEND chunk.
    """
    if instrument is None:
        from .errors import DPONotConnectedError

        raise DPONotConnectedError("Oscilloscope is not connected.")

    try:
        old_timeout = getattr(instrument, "timeout")
    except Exception:
        old_timeout = None
    try:
        transfer_timeout = max(int(old_timeout or 0), int(timeout_ms))
    except (TypeError, ValueError):
        transfer_timeout = int(timeout_ms)

    previous_format = _read_hardcopy_format(instrument)
    primary_error: BaseException | None = None

    try:
        with temporary_session_attributes(
            instrument,
            timeout=transfer_timeout,
            read_termination=None,
            write_termination="\n",
        ):
            try:
                instrument.write("HARDCOPY:FORMAT PNG")
                if command_delay_s:
                    time.sleep(command_delay_s)
                instrument.write("HARDCOPY START")
                transfer_started = time.perf_counter()
                payload = _read_hardcopy_payload(instrument)
                png = require_png_bytes(payload)
                logger.debug(
                    "Hardcopy transfer completed in %.3fs (%d PNG bytes)",
                    time.perf_counter() - transfer_started,
                    len(png),
                )
                return png
            except DPOError:
                raise
            except Exception as exc:
                if is_transport_error(exc):
                    raise transport_exception(exc, "Capturing scope hardcopy") from exc
                raise HardcopyCaptureError(f"Scope hardcopy capture failed: {exc}") from exc
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        if previous_format and previous_format != "PNG":
            try:
                instrument.write(f"HARDCOPY:FORMAT {previous_format}")
            except BaseException as restore_exc:
                if primary_error is not None:
                    add_exception_note(
                        primary_error,
                        f"Could not restore HARDCOPY:FORMAT {previous_format}: {restore_exc}",
                    )
                    logger.warning(
                        "Could not restore HARDCOPY:FORMAT %s after capture failure: %s",
                        previous_format,
                        restore_exc,
                    )
                else:
                    raise HardcopyCaptureError(
                        f"Captured image but could not restore HARDCOPY:FORMAT {previous_format}: "
                        f"{restore_exc}"
                    ) from restore_exc


def save_screen_png(instrument: Any, path: str | Path, *, timeout_ms: int = 60_000) -> Path:
    """Capture the oscilloscope display and save it as a clean PNG file."""
    file_path = Path(path)
    png_data = capture_screen_png(instrument, timeout_ms=timeout_ms)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(png_data)
    return file_path


class HardcopyMixin:
    """Mixin for screen image capture."""

    def read_screen_png(self) -> bytes:
        """Capture current oscilloscope screen and return PNG bytes."""
        return capture_screen_png(self.ensure_connected())

    def save_image_path(self, path=""):
        """Save current oscilloscope screen as a PNG file."""
        return save_screen_png(self.ensure_connected(), path)


__all__ = [
    "HardcopyCaptureError",
    "PNG_IEND",
    "PNG_SIGNATURE",
    "capture_screen_png",
    "extract_png_bytes",
    "hardcopy_response_prefix",
    "require_png_bytes",
    "save_screen_png",
    "strip_ieee_block_header",
    "trim_png_after_iend",
]
