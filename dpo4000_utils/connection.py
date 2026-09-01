"""Connection helpers and VISA resource handling."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .errors import (
    DPOCleanupError,
    DPOConnectionError,
    DPOError,
    DPONotConnectedError,
    DPOTimeoutError,
    DPOTransportError,
    add_exception_note,
    is_timeout_error,
    transport_exception,
)

try:
    import pyvisa
except Exception as exc:  # Import lazily enough that docs/tests can import package.
    pyvisa = None
    VISA_IMPORT_ERROR = exc
else:
    VISA_IMPORT_ERROR = None


logger = logging.getLogger(__name__)

# Retained only for source compatibility with older scripts. New driver instances
# no longer select a physical serial number implicitly.
LEGACY_VISA_RESOURCE = "USB0::0x0699::0x0401::C011280::INSTR"
visaResourceAddr = LEGACY_VISA_RESOURCE


def build_tcpip_instr_resource(host: str) -> str:
    """Build a VXI-11/INSTR VISA resource string for Ethernet scopes."""
    host = host.strip()
    if not host:
        raise ValueError("host must not be empty")
    return f"TCPIP0::{host}::INSTR"


def build_tcpip_socket_resource(host: str, port: int | str = 4000) -> str:
    """Build a raw TCP socket VISA resource string for Ethernet scopes."""
    host = host.strip()
    if not host:
        raise ValueError("host must not be empty")
    port_int = int(port)
    if port_int <= 0 or port_int > 65535:
        raise ValueError("port must be between 1 and 65535")
    return f"TCPIP0::{host}::{port_int}::SOCKET"


def list_visa_resources() -> tuple[str, ...]:
    """Return VISA resources visible through the configured VISA backend."""
    if pyvisa is None:
        raise DPOConnectionError(
            "PyVISA is not available. Install pyvisa and a VISA runtime such as "
            "NI-VISA, TekVISA, or Keysight VISA."
        ) from VISA_IMPORT_ERROR

    try:
        rm = pyvisa.ResourceManager()
    except Exception as exc:
        raise transport_exception(exc, "Opening VISA resource manager") from exc
    try:
        try:
            return tuple(rm.list_resources())
        except Exception as exc:
            raise transport_exception(exc, "Listing VISA resources") from exc
    finally:
        try:
            rm.close()
        except Exception as exc:  # Discovery result/error remains primary.
            logger.warning("Could not close VISA resource manager after discovery: %s", exc)


def _close_visa_parts(instrument: Any, resource_manager: Any) -> list[BaseException]:
    """Attempt to close both VISA objects and return cleanup failures in order."""
    failures: list[BaseException] = []
    if instrument is not None:
        try:
            instrument.close()
        except BaseException as exc:  # cleanup must continue through backend defects.
            failures.append(exc)
    if resource_manager is not None:
        try:
            resource_manager.close()
        except BaseException as exc:
            failures.append(exc)
    return failures


@contextmanager
def temporary_session_attributes(instrument: Any, **attributes: Any) -> Iterator[Any]:
    """Temporarily set VISA-session attributes and restore exact original values.

    Missing attributes are skipped. Setter/restoration failures are surfaced as
    driver transport errors when they are the primary failure. If the operation
    inside the context already failed, restoration diagnostics are attached to
    that exception (Python 3.11+) or logged instead of replacing it.
    """
    originals: list[tuple[str, Any]] = []
    primary_error: BaseException | None = None
    try:
        for name, temporary_value in attributes.items():
            try:
                original_value = getattr(instrument, name)
            except (AttributeError, NotImplementedError):
                continue
            except Exception as exc:
                raise transport_exception(exc, f"Reading VISA attribute {name}") from exc

            originals.append((name, original_value))
            try:
                setattr(instrument, name, temporary_value)
            except Exception as exc:
                raise transport_exception(exc, f"Setting VISA attribute {name}") from exc

        yield instrument
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        restore_failures: list[tuple[str, BaseException]] = []
        for name, original_value in reversed(originals):
            try:
                setattr(instrument, name, original_value)
            except BaseException as exc:
                restore_failures.append((name, exc))

        if restore_failures:
            details = "; ".join(f"{name}: {error}" for name, error in restore_failures)
            if primary_error is not None:
                add_exception_note(
                    primary_error, f"VISA attribute restoration failure(s): {details}"
                )
                logger.warning("VISA attribute restoration failure(s): %s", details)
            else:
                first = restore_failures[0][1]
                raise DPOTransportError(
                    f"Could not restore VISA session attribute(s): {details}"
                ) from first


class ConnectionMixin:
    """Mixin providing VISA session lifecycle helpers."""

    def _apply_session_configuration(self) -> None:
        """Apply driver-owned VISA session options before the first query."""
        if self.scope is None:
            return

        timeout_ms = getattr(self, "timeout_ms", None)
        if timeout_ms is not None:
            timeout_value = int(timeout_ms)
            if timeout_value <= 0:
                raise ValueError("timeout_ms must be a positive integer")
            self.scope.timeout = timeout_value

        read_termination = getattr(self, "read_termination", None)
        if read_termination is not None:
            self.scope.read_termination = read_termination

        write_termination = getattr(self, "write_termination", None)
        if write_termination is not None:
            self.scope.write_termination = write_termination

    def connect(self):
        """Connect to the oscilloscope. Safe to call multiple times."""
        if self.scope is not None:
            return

        resource_name = str(getattr(self, "resource_name", "") or "").strip()
        if not resource_name:
            raise DPOConnectionError(
                "No VISA resource was configured. Pass resource_name explicitly or select "
                "a resource through the GUI/discovery API."
            )

        if pyvisa is None:
            raise DPOConnectionError(
                "PyVISA is not available. Install pyvisa and a VISA runtime such as "
                "NI-VISA, TekVISA, or Keysight VISA."
            ) from VISA_IMPORT_ERROR

        try:
            if self.rm is None:
                self.rm = pyvisa.ResourceManager()
            self.scope = self.rm.open_resource(resource_name)
            self._apply_session_configuration()
            idn = self.scope.query("*IDN?").strip()
            logger.info("Connected to Tektronix scope resource=%s idn=%s", resource_name, idn)
        except BaseException as exc:
            instrument = self.scope
            resource_manager = self.rm
            self.scope = None
            self.rm = None
            cleanup_failures = _close_visa_parts(instrument, resource_manager)
            if cleanup_failures:
                details = "; ".join(str(item) for item in cleanup_failures)
                add_exception_note(exc, f"Connection cleanup failure(s): {details}")
                logger.warning("Connection cleanup failure(s): %s", details)

            if isinstance(exc, DPOError):
                raise
            if is_timeout_error(exc):
                raise DPOTimeoutError(
                    f"Failed to connect to oscilloscope resource {resource_name}: {exc}"
                ) from exc
            raise DPOConnectionError(
                f"Failed to connect to oscilloscope resource {resource_name}: {exc}"
            ) from exc

    def disconnect(self):
        """Release instrument and resource manager; always leave disconnected state."""
        instrument = self.scope
        resource_manager = self.rm
        # Clear references first so a failed backend close cannot leave stale live state.
        self.scope = None
        self.rm = None

        failures = _close_visa_parts(instrument, resource_manager)
        if failures:
            detail = "; ".join(str(item) for item in failures)
            raise DPOCleanupError(f"Failed to fully close VISA session: {detail}") from failures[0]

    def ensure_connected(self):
        """Return the active scope session or raise the stable not-connected error."""
        if self.scope is None:
            raise DPONotConnectedError("Oscilloscope not connected. Call connect() first.")
        return self.scope

    @contextmanager
    def temporary_timeout(self, timeout_ms: int):
        """Temporarily cap the active VISA timeout and restore it afterwards."""
        timeout_value = int(timeout_ms)
        if timeout_value <= 0:
            raise ValueError("timeout_ms must be a positive integer")

        instrument = self.ensure_connected()
        try:
            previous_timeout = instrument.timeout
        except (AttributeError, NotImplementedError):
            yield instrument
            return

        if previous_timeout is None:
            effective_timeout = timeout_value
        else:
            try:
                effective_timeout = min(int(previous_timeout), timeout_value)
            except (TypeError, ValueError):
                effective_timeout = timeout_value

        with temporary_session_attributes(instrument, timeout=effective_timeout):
            yield instrument

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, traceback):
        try:
            self.disconnect()
        except BaseException as cleanup_exc:
            if exc is None:
                raise
            add_exception_note(exc, f"Disconnect cleanup failure: {cleanup_exc}")
            logger.warning(
                "Disconnect cleanup failure while propagating primary error: %s", cleanup_exc
            )
        return False


__all__ = [
    "LEGACY_VISA_RESOURCE",
    "ConnectionMixin",
    "build_tcpip_instr_resource",
    "build_tcpip_socket_resource",
    "list_visa_resources",
    "temporary_session_attributes",
    "visaResourceAddr",
]
