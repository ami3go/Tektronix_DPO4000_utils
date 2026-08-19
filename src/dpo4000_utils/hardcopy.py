"""Screen hardcopy capture helpers."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_IEND = b"IEND\xaeB`\x82"


class HardcopyCaptureError(RuntimeError):
    """Raised when the scope response cannot be converted to a valid PNG."""


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
    """Extract a clean PNG stream from Tektronix hardcopy response bytes.

    This function is intentionally permissive for backwards compatibility: if no
    PNG signature is found, it returns the stripped payload. Use
    :func:`require_png_bytes` when callers need validation and diagnostics.
    """
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


def capture_screen_png(
    instrument: Any,
    *,
    timeout_ms: int = 60_000,
    command_delay_s: float = 0.03,
) -> bytes:
    """Capture the oscilloscope display and return validated PNG bytes.

    ``instrument`` is expected to be a PyVISA-like session object with
    ``write()`` and ``read_raw()`` methods. The function temporarily adjusts
    binary-transfer related VISA attributes and restores them before returning.
    """
    if instrument is None:
        raise ConnectionError("Oscilloscope is not connected.")

    old_timeout = getattr(instrument, "timeout", None)
    old_read_termination = getattr(instrument, "read_termination", None)
    old_write_termination = getattr(instrument, "write_termination", None)

    try:
        try:
            instrument.timeout = max(int(old_timeout or 0), int(timeout_ms))
        except Exception:
            pass

        try:
            instrument.read_termination = None
        except Exception:
            pass
        try:
            instrument.write_termination = "\n"
        except Exception:
            pass

        for command in (
            "*CLS",
            "HEADER OFF",
            "VERBOSE OFF",
            "HARDCOPY:FORMAT PNG",
            "SAVE:IMAGE:FILEFORMAT PNG",
            "SAVE:IMAGE:INKSAVER OFF",
        ):
            try:
                instrument.write(command)
                time.sleep(command_delay_s)
            except Exception:
                pass

        try:
            instrument.write("HARDCOPY START")
        except Exception:
            instrument.write("HARDCOPY:START")

        return require_png_bytes(instrument.read_raw())
    finally:
        try:
            if old_timeout is not None:
                instrument.timeout = old_timeout
        except Exception:
            pass
        try:
            instrument.read_termination = old_read_termination
        except Exception:
            pass
        try:
            instrument.write_termination = old_write_termination
        except Exception:
            pass


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
