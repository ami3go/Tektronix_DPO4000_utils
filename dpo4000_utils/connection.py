"""Connection helpers and VISA resource handling."""

from __future__ import annotations

from contextlib import contextmanager

try:
    import pyvisa
except Exception as exc:  # Import lazily enough that docs/tests can import package.
    pyvisa = None
    VISA_IMPORT_ERROR = exc
else:
    VISA_IMPORT_ERROR = None


visaResourceAddr = "USB0::0x0699::0x0401::C011280::INSTR"


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
        raise ConnectionError(
            "PyVISA is not available. Install pyvisa and a VISA runtime such as "
            "NI-VISA, TekVISA, or Keysight VISA."
        ) from VISA_IMPORT_ERROR

    rm = pyvisa.ResourceManager()
    try:
        return tuple(rm.list_resources())
    finally:
        rm.close()


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

        if pyvisa is None:
            raise ConnectionError(
                "PyVISA is not available. Install pyvisa and a VISA runtime such as "
                "NI-VISA, TekVISA, or Keysight VISA."
            ) from VISA_IMPORT_ERROR

        try:
            if self.rm is None:
                self.rm = pyvisa.ResourceManager()
            self.scope = self.rm.open_resource(self.resource_name)
            self._apply_session_configuration()
            idn = self.scope.query("*IDN?").strip()
            print(f"Connected to: {idn}")
        except Exception as exc:
            if self.scope is not None:
                try:
                    self.scope.close()
                except Exception:
                    pass
                self.scope = None
            if self.rm is not None:
                try:
                    self.rm.close()
                except Exception:
                    pass
                self.rm = None
            raise ConnectionError(f"Failed to connect to the oscilloscope: {exc}") from exc

    def disconnect(self):
        """Disconnect oscilloscope and release the VISA resource manager."""
        if self.scope is not None:
            self.scope.close()
            self.scope = None

        if self.rm is not None:
            self.rm.close()
            self.rm = None

    def ensure_connected(self):
        """Return the active scope session or raise a clear connection error."""
        if self.scope is None:
            raise ConnectionError("Oscilloscope not connected. Call connect() first.")
        return self.scope

    @contextmanager
    def temporary_timeout(self, timeout_ms: int):
        """Temporarily cap the active VISA timeout and restore it afterwards.

        This is used by capability/optional-feature discovery so an unsupported
        command cannot consume the full user-configured timeout repeatedly.
        """
        timeout_value = int(timeout_ms)
        if timeout_value <= 0:
            raise ValueError("timeout_ms must be a positive integer")

        instrument = self.ensure_connected()
        previous_timeout = getattr(instrument, "timeout", None)
        if previous_timeout is None:
            effective_timeout = timeout_value
        else:
            try:
                effective_timeout = min(int(previous_timeout), timeout_value)
            except (TypeError, ValueError):
                effective_timeout = timeout_value

        instrument.timeout = effective_timeout
        try:
            yield instrument
        finally:
            if previous_timeout is not None:
                instrument.timeout = previous_timeout

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.disconnect()
        return False
