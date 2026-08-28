"""Project-specific exceptions and transport classification helpers."""

from __future__ import annotations

from typing import Any


VI_ERROR_TMO = -1073807339


class DPOError(Exception):
    """Base exception for all public DPO4000 utility failures."""


class DPOConnectionError(ConnectionError, DPOError):
    """Raised when the oscilloscope cannot be connected or used."""


class DPONotConnectedError(DPOConnectionError):
    """Raised when an operation requires an open oscilloscope session."""


class DPOTransportError(DPOConnectionError):
    """Raised for VISA/backend transport or lost-session failures."""


class DPOTimeoutError(TimeoutError, DPOTransportError):
    """Raised when a VISA/backend operation times out."""


class DPOCleanupError(DPOConnectionError):
    """Raised when VISA resources cannot be fully released."""


class DPOProtocolError(DPOError):
    """Raised when instrument data or a SCPI protocol exchange is invalid."""


class DPOImageCaptureError(DPOProtocolError):
    """Raised when screen hardcopy data cannot be captured or parsed."""


class DPOSettingsError(DPOProtocolError):
    """Raised when scope setup save/restore data is invalid or cannot be applied."""


class DPOWaveformError(RuntimeError, DPOProtocolError):
    """Raised when waveform transfer, decoding, scaling, or alignment is invalid."""


def _error_code_value(exc: BaseException) -> int | None:
    code: Any = getattr(exc, "error_code", None)
    if code is None:
        return None
    raw = getattr(code, "value", code)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def is_timeout_error(exc: BaseException) -> bool:
    """Return True for Python or PyVISA-style timeout failures."""
    if isinstance(exc, DPOTimeoutError | TimeoutError):
        return True
    if _error_code_value(exc) == VI_ERROR_TMO:
        return True
    text = f"{exc.__class__.__name__} {exc}".upper()
    return "VI_ERROR_TMO" in text or "TIMEOUT" in text or "TIMED OUT" in text


def is_transport_error(exc: BaseException) -> bool:
    """Return True when *exc* represents connection/VISA transport failure."""
    if isinstance(exc, (DPOTransportError, DPOTimeoutError, DPONotConnectedError)):
        return True
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    if getattr(exc, "error_code", None) is not None:
        return True
    module = exc.__class__.__module__.lower()
    return module.startswith("pyvisa") or ".pyvisa" in module


def transport_exception(exc: BaseException, operation: str) -> DPOTransportError:
    """Translate a backend exception to the stable public transport contract."""
    detail = str(exc).strip() or exc.__class__.__name__
    if is_timeout_error(exc):
        return DPOTimeoutError(f"{operation} timed out: {detail}")
    return DPOTransportError(f"{operation} failed: {detail}")


def add_exception_note(exc: BaseException, note: str) -> None:
    """Attach cleanup/secondary diagnostic text without replacing a primary error."""
    add_note = getattr(exc, "add_note", None)
    if callable(add_note):
        add_note(note)


__all__ = [
    "DPOCleanupError",
    "DPOConnectionError",
    "DPOError",
    "DPOImageCaptureError",
    "DPONotConnectedError",
    "DPOProtocolError",
    "DPOSettingsError",
    "DPOTimeoutError",
    "DPOTransportError",
    "DPOWaveformError",
    "VI_ERROR_TMO",
    "add_exception_note",
    "is_timeout_error",
    "is_transport_error",
    "transport_exception",
]
