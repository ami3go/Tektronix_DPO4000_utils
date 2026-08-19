"""Connection and form-validation helpers for the GUI.

These helpers keep small pieces of GUI state handling testable without creating a
Tkinter window. They are used by the persistent GUI wrapper while the large base
window is being decomposed incrementally.
"""

from __future__ import annotations

ETHERNET_VXI11_PROTOCOL = "VXI-11 / INSTR"
ETHERNET_SOCKET_PROTOCOL = "Raw SOCKET"
VALID_TRIGGER_CHANNELS = {"1", "2", "3", "4"}
TRIGGER_LEVEL_PRESETS = {"TTL", "ECL"}


def build_ethernet_resource(host: str, protocol: str, port: str | int = "4000") -> str:
    """Build a VISA TCPIP resource string from Ethernet form fields."""
    host = (host or "").strip()
    if not host:
        raise ValueError("Ethernet IP/host cannot be empty.")

    protocol = (protocol or ETHERNET_VXI11_PROTOCOL).strip()
    if protocol == ETHERNET_SOCKET_PROTOCOL:
        try:
            port_number = int(str(port).strip())
        except ValueError as exc:
            raise ValueError("Ethernet socket port must be an integer.") from exc
        if port_number < 1 or port_number > 65535:
            raise ValueError("Ethernet socket port must be between 1 and 65535.")
        return f"TCPIP0::{host}::{port_number}::SOCKET"

    return f"TCPIP0::{host}::INSTR"


def selected_resource_name(
    connection_mode: str,
    visa_resource: str,
    ethernet_host: str,
    ethernet_protocol: str,
    ethernet_port: str | int,
) -> str:
    """Return the VISA resource selected by current connection form values."""
    if (connection_mode or "").strip() == "ethernet":
        return build_ethernet_resource(ethernet_host, ethernet_protocol, ethernet_port)

    resource = (visa_resource or "").strip()
    if not resource:
        raise ValueError("VISA resource cannot be empty.")
    return resource


def parse_timeout_ms(raw_timeout: str | int, *, minimum_ms: int = 1000) -> int:
    """Parse and validate a GUI timeout field."""
    try:
        timeout = int(str(raw_timeout).strip())
    except ValueError as exc:
        raise ValueError("Timeout must be an integer number of milliseconds.") from exc
    if timeout < minimum_ms:
        raise ValueError(f"Timeout should be at least {minimum_ms} ms.")
    return timeout


def parse_trigger_channel(value: str | int, *, allow_empty: bool = False) -> int | None:
    """Parse a trigger channel combobox value."""
    text = str(value).strip()
    if allow_empty and not text:
        return None
    if text not in VALID_TRIGGER_CHANNELS:
        raise ValueError("Trigger source channel must be 1, 2, 3, or 4.")
    return int(text)


def parse_trigger_level(value: str | float | int) -> float | str:
    """Parse a trigger level field as volts or a supported Tektronix preset."""
    text = str(value).strip()
    if not text:
        raise ValueError("Trigger level cannot be empty.")

    preset = text.upper()
    if preset in TRIGGER_LEVEL_PRESETS:
        return preset

    try:
        return float(text)
    except ValueError as exc:
        raise ValueError("Trigger level must be a number in volts, or TTL/ECL.") from exc
