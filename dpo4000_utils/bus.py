"""Serial/parallel bus support for Tektronix DPO4000-family oscilloscopes."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any

from .control import normalize_scope_response_text, quote_scpi_string, scpi_bool
from .errors import is_transport_error, transport_exception
from .io_policy import optional_query
from .scpi_values import (
    ensure_single_scpi_value,
    format_scpi_number,
    normalize_scpi_enum,
)

BUS_SLOTS = (1, 2, 3, 4)
BUS_COUNT_QUERY = "CONFIGURATION:BUSWAVEFORMS:NUMBUS?"
BUS_CAPABILITY_TIMEOUT_MS = 1000
BUS_TYPES = (
    "I2C",
    "SPI",
    "CAN",
    "RS232C",
    "LIN",
    "FLEXRAY",
    "AUDIO",
    "USB",
    "PARALLEL",
)
BUS_DISPLAY_FORMATS = (
    "BINARY",
    "HEXADECIMAL",
    "ASCII",
    "MIXED",
    "MIXED2",
    "SIGNEDDECIMAL",
)
BUS_DISPLAY_TYPES = ("BUS", "BOTH")

BUS_COMMON_COMMANDS = {
    "state": "BUS:B{bus}:STATE",
    "type": "BUS:B{bus}:TYPE",
    "label": "BUS:B{bus}:LABEL",
    "position": "BUS:B{bus}:POSITION",
    "display_format": "BUS:B{bus}:DISPLAY:FORMAT",
    "display_type": "BUS:B{bus}:DISPLAY:TYPE",
}


def _parallel_commands() -> dict[str, str]:
    commands = {f"bit{bit}_source": f"BUS:B{{bus}}:PARALLEL:BIT{bit}:SOURCE" for bit in range(16)}
    commands.update(
        {
            "clock_edge": "BUS:B{bus}:PARALLEL:CLOCK:EDGE",
            "clock_is_clocked": "BUS:B{bus}:PARALLEL:CLOCK:ISCLOCKED",
            "clock_source": "BUS:B{bus}:PARALLEL:CLOCK:SOURCE",
            "width": "BUS:B{bus}:PARALLEL:WIDTH",
        }
    )
    return commands


BUS_PROTOCOL_COMMANDS: dict[str, dict[str, str]] = {
    "AUDIO": {
        "bit_delay": "BUS:B{bus}:AUDIO:BITDELAY",
        "bit_order": "BUS:B{bus}:AUDIO:BITORDER",
        "channel_size": "BUS:B{bus}:AUDIO:CHANNEL:SIZE",
        "clock_polarity": "BUS:B{bus}:AUDIO:CLOCK:POLARITY",
        "clock_source": "BUS:B{bus}:AUDIO:CLOCK:SOURCE",
        "data_polarity": "BUS:B{bus}:AUDIO:DATA:POLARITY",
        "data_size": "BUS:B{bus}:AUDIO:DATA:SIZE",
        "data_source": "BUS:B{bus}:AUDIO:DATA:SOURCE",
        "audio_display_format": "BUS:B{bus}:AUDIO:DISPLAY:FORMAT",
        "frame_size": "BUS:B{bus}:AUDIO:FRAME:SIZE",
        "frame_sync_polarity": "BUS:B{bus}:AUDIO:FRAMESYNC:POLARITY",
        "frame_sync_source": "BUS:B{bus}:AUDIO:FRAMESYNC:SOURCE",
        "audio_type": "BUS:B{bus}:AUDIO:TYPE",
        "word_select_polarity": "BUS:B{bus}:AUDIO:WORDSEL:POLARITY",
        "word_select_source": "BUS:B{bus}:AUDIO:WORDSEL:SOURCE",
    },
    "CAN": {
        "bit_rate": "BUS:B{bus}:CAN:BITRATE",
        "probe": "BUS:B{bus}:CAN:PROBE",
        "sample_point": "BUS:B{bus}:CAN:SAMPLEPOINT",
        "source": "BUS:B{bus}:CAN:SOURCE",
    },
    "FLEXRAY": {
        "bit_rate": "BUS:B{bus}:FLEXRAY:BITRATE",
        "channel": "BUS:B{bus}:FLEXRAY:CHANNEL",
        "signal": "BUS:B{bus}:FLEXRAY:SIGNAL",
        "source": "BUS:B{bus}:FLEXRAY:SOURCE",
    },
    "I2C": {
        "address_rw_include": "BUS:B{bus}:I2C:ADDRESS:RWINCLUDE",
        "clock_source": "BUS:B{bus}:I2C:CLOCK:SOURCE",
        "data_source": "BUS:B{bus}:I2C:DATA:SOURCE",
    },
    "LIN": {
        "bit_rate": "BUS:B{bus}:LIN:BITRATE",
        "id_format": "BUS:B{bus}:LIN:IDFORMAT",
        "polarity": "BUS:B{bus}:LIN:POLARITY",
        "sample_point": "BUS:B{bus}:LIN:SAMPLEPOINT",
        "source": "BUS:B{bus}:LIN:SOURCE",
        "standard": "BUS:B{bus}:LIN:STANDARD",
    },
    "PARALLEL": _parallel_commands(),
    "RS232C": {
        "bit_rate": "BUS:B{bus}:RS232C:BITRATE",
        "data_bits": "BUS:B{bus}:RS232C:DATABITS",
        "delimiter": "BUS:B{bus}:RS232C:DELIMITER",
        "display_mode": "BUS:B{bus}:RS232C:DISPLAYMODE",
        "parity": "BUS:B{bus}:RS232C:PARITY",
        "polarity": "BUS:B{bus}:RS232C:POLARITY",
        "rx_source": "BUS:B{bus}:RS232C:RX:SOURCE",
        "tx_source": "BUS:B{bus}:RS232C:TX:SOURCE",
    },
    "SPI": {
        "bit_order": "BUS:B{bus}:SPI:BITORDER",
        "clock_polarity": "BUS:B{bus}:SPI:CLOCK:POLARITY",
        "clock_source": "BUS:B{bus}:SPI:CLOCK:SOURCE",
        "miso_polarity": "BUS:B{bus}:SPI:DATA:MISO:POLARITY",
        "miso_source": "BUS:B{bus}:SPI:DATA:MISO:SOURCE",
        "mosi_polarity": "BUS:B{bus}:SPI:DATA:MOSI:POLARITY",
        "mosi_source": "BUS:B{bus}:SPI:DATA:MOSI:SOURCE",
        "data_size": "BUS:B{bus}:SPI:DATA:SIZE",
        "framing": "BUS:B{bus}:SPI:FRAMING",
        "idle_time": "BUS:B{bus}:SPI:IDLETIME",
        "ss_polarity": "BUS:B{bus}:SPI:SS:POLARITY",
        "ss_source": "BUS:B{bus}:SPI:SS:SOURCE",
    },
    "USB": {
        "bit_rate": "BUS:B{bus}:USB:BITRATE",
        "probe": "BUS:B{bus}:USB:PROBE",
        "differential_source": "BUS:B{bus}:USB:SOURCE:DIFFERENTIAL",
        "dminus_source": "BUS:B{bus}:USB:SOURCE:DMINUS",
        "dplus_source": "BUS:B{bus}:USB:SOURCE:DPLUS",
    },
}

_BUS_TYPE_ALIASES = {
    "AUD": "AUDIO",
    "AUDIO": "AUDIO",
    "CAN": "CAN",
    "FLEX": "FLEXRAY",
    "FLEXRAY": "FLEXRAY",
    "I2C": "I2C",
    "LIN": "LIN",
    "PAR": "PARALLEL",
    "PARALLEL": "PARALLEL",
    "RS232": "RS232C",
    "RS232C": "RS232C",
    "SPI": "SPI",
    "USB": "USB",
}

_BUS_DISPLAY_FORMAT_ALIASES = {
    "BIN": "BINARY",
    "HEX": "HEXADECIMAL",
    "SIGNED": "SIGNEDDECIMAL",
    "SIGNEDDEC": "SIGNEDDECIMAL",
}


@dataclass(frozen=True)
class BusConfig:
    """Writable configuration for one BUS1..BUS4 waveform."""

    bus: int
    state: bool | None = None
    bus_type: str | None = None
    label: str | None = None
    position: str | float | int | None = None
    display_format: str | None = None
    display_type: str | None = None
    protocol_settings: Mapping[str, Any] = field(default_factory=dict)


def normalize_bus(bus: int | str) -> int:
    """Validate and normalize a BUS waveform number."""
    try:
        value = int(bus)
    except (TypeError, ValueError) as exc:
        raise ValueError("Bus waveform must be an integer from 1 to 4.") from exc
    if value not in BUS_SLOTS:
        raise ValueError("Bus waveform must be between 1 and 4.")
    return value


def canonical_bus_type(bus_type: str | None) -> str:
    """Return a stable safe bus-type token, preserving unknown future types."""
    if bus_type is None:
        return ""
    raw = ensure_single_scpi_value(bus_type, field="BUS type", allow_empty=True)
    if not raw:
        return ""
    compact = raw.upper().replace("-", "").replace("_", "").replace(" ", "")
    return _BUS_TYPE_ALIASES.get(compact, compact)


def bus_protocol_fields(bus_type: str | None) -> tuple[str, ...]:
    """Return writable protocol-specific fields for a bus type."""
    return tuple(BUS_PROTOCOL_COMMANDS.get(canonical_bus_type(bus_type), {}))


def bus_protocol_field_label(field_name: str) -> str:
    """Create a concise human-readable label for a protocol field."""
    aliases = {
        "rw": "R/W",
        "rx": "RX",
        "tx": "TX",
        "miso": "MISO",
        "mosi": "MOSI",
        "ss": "SS",
        "dminus": "D−",
        "dplus": "D+",
    }
    words: list[str] = []
    for part in str(field_name).split("_"):
        if part in aliases:
            words.append(aliases[part])
        elif part.startswith("bit") and part[3:].isdigit():
            words.append(f"Bit {part[3:]}")
        else:
            words.append(part.capitalize())
    return " ".join(words)


def build_bus_config_queries(bus: int | str) -> dict[str, str]:
    """Build common BUS channel readback queries."""
    valid_bus = normalize_bus(bus)
    return {
        name: f"{command.format(bus=valid_bus)}?" for name, command in BUS_COMMON_COMMANDS.items()
    }


def build_bus_protocol_queries(bus: int | str, bus_type: str | None) -> dict[str, str]:
    """Build protocol-specific readback queries for one BUS channel."""
    valid_bus = normalize_bus(bus)
    commands = BUS_PROTOCOL_COMMANDS.get(canonical_bus_type(bus_type), {})
    return {name: f"{command.format(bus=valid_bus)}?" for name, command in commands.items()}


def _command_value(value: Any, *, field: str) -> str:
    if isinstance(value, bool):
        return scpi_bool(value)
    return ensure_single_scpi_value(value, field=field)


def build_bus_config_commands(config: BusConfig) -> list[str]:
    """Build BUS configuration commands in an order safe for protocol changes."""
    bus = normalize_bus(config.bus)
    bus_type = canonical_bus_type(config.bus_type)
    commands: list[str] = []

    if bus_type:
        commands.append(f"BUS:B{bus}:TYPE {bus_type}")

    protocol_commands = BUS_PROTOCOL_COMMANDS.get(bus_type, {})
    provided = {str(name): value for name, value in config.protocol_settings.items()}
    unknown = sorted(set(provided) - set(protocol_commands))
    if unknown:
        raise ValueError(
            f"Unsupported {bus_type or 'bus'} protocol setting(s): {', '.join(unknown)}."
        )
    for name, command in protocol_commands.items():
        if name not in provided:
            continue
        text = _command_value(provided[name], field=f"{bus_type} {name}")
        if text:
            commands.append(f"{command.format(bus=bus)} {text}")

    if config.label is not None:
        commands.append(f"BUS:B{bus}:LABEL {quote_scpi_string(str(config.label)[:30])}")

    if config.position is not None:
        position = format_scpi_number(config.position, field="BUS position")
        commands.append(f"BUS:B{bus}:POSITION {position}")

    if config.display_format is not None:
        display_format = normalize_scpi_enum(
            config.display_format,
            BUS_DISPLAY_FORMATS,
            field="BUS display format",
            aliases=_BUS_DISPLAY_FORMAT_ALIASES,
        )
        commands.append(f"BUS:B{bus}:DISPLAY:FORMAT {display_format}")

    if config.display_type is not None:
        display_type = normalize_scpi_enum(
            config.display_type,
            BUS_DISPLAY_TYPES,
            field="BUS display type",
        )
        commands.append(f"BUS:B{bus}:DISPLAY:TYPE {display_type}")

    if config.state is not None:
        commands.append(f"BUS:B{bus}:STATE {scpi_bool(config.state)}")

    return commands


def _capability_timeout_context(driver: Any, timeout_ms: int):
    temporary_timeout = getattr(driver, "temporary_timeout", None)
    if callable(temporary_timeout):
        return temporary_timeout(timeout_ms)
    return nullcontext()


def _confirm_transport_alive(instrument: Any, failure: BaseException, operation: str) -> None:
    """Allow unsupported-command timeouts only when the session still answers IDN."""
    if not is_transport_error(failure):
        raise failure
    try:
        instrument.query("*IDN?")
    except Exception as health_exc:
        raise transport_exception(health_exc, f"{operation}; session health check") from health_exc


class BusMixin:
    """Public high-level API for DPO4000 BUS waveforms."""

    @staticmethod
    def _query_bus_optional(instrument: Any, command: str) -> str:
        return optional_query(instrument, command, normalizer=normalize_scope_response_text)

    def probe_bus_support(self, bus: int | str = 1) -> bool:
        """Probe one BUS slot with a single required query."""
        valid_bus = normalize_bus(bus)
        scope = self.ensure_connected()
        query = build_bus_config_queries(valid_bus)["type"]
        response = normalize_scope_response_text(scope.query(query).strip())
        return bool(response)

    def get_bus_waveform_count(self, *, timeout_ms: int = BUS_CAPABILITY_TIMEOUT_MS) -> int:
        """Return BUS waveform count with bounded older-firmware fallback."""
        instrument = self.ensure_connected()
        with _capability_timeout_context(self, timeout_ms):
            try:
                response = normalize_scope_response_text(instrument.query(BUS_COUNT_QUERY).strip())
                count = int(float(response))
                return max(0, min(len(BUS_SLOTS), count))
            except Exception as exc:
                _confirm_transport_alive(instrument, exc, "Reading BUS waveform count")

            count = 0
            for bus in BUS_SLOTS:
                query = build_bus_config_queries(bus)["type"]
                try:
                    response = normalize_scope_response_text(instrument.query(query).strip())
                except Exception as exc:
                    _confirm_transport_alive(instrument, exc, f"Probing BUS{bus}")
                    break
                if not response:
                    break
                count = bus
            return count

    def get_available_bus_slots(
        self, *, timeout_ms: int = BUS_CAPABILITY_TIMEOUT_MS
    ) -> tuple[int, ...]:
        """Return actual BUS slot numbers exposed by the connected scope."""
        return BUS_SLOTS[: self.get_bus_waveform_count(timeout_ms=timeout_ms)]

    def get_bus_configuration(self, bus: int | str) -> dict[str, Any]:
        """Read common and active-protocol settings for one BUS waveform."""
        valid_bus = normalize_bus(bus)
        scope = self.ensure_connected()
        values: dict[str, Any] = {
            name: self._query_bus_optional(scope, query)
            for name, query in build_bus_config_queries(valid_bus).items()
        }
        bus_type = canonical_bus_type(values.get("type", ""))
        if bus_type:
            values["type"] = bus_type
        values["protocol"] = {
            name: self._query_bus_optional(scope, query)
            for name, query in build_bus_protocol_queries(valid_bus, bus_type).items()
        }
        return values

    def get_all_bus_configurations(self) -> dict[int, dict[str, Any]]:
        """Read configurations only for BUS slots exposed by the scope."""
        return {bus: self.get_bus_configuration(bus) for bus in self.get_available_bus_slots()}

    def configure_bus(self, config: BusConfig) -> None:
        """Apply common and protocol-specific settings to one BUS waveform."""
        scope = self.ensure_connected()
        for command in build_bus_config_commands(config):
            scope.write(command)


__all__ = [
    "BUS_CAPABILITY_TIMEOUT_MS",
    "BUS_COMMON_COMMANDS",
    "BUS_COUNT_QUERY",
    "BUS_DISPLAY_FORMATS",
    "BUS_DISPLAY_TYPES",
    "BUS_PROTOCOL_COMMANDS",
    "BUS_SLOTS",
    "BUS_TYPES",
    "BusConfig",
    "BusMixin",
    "build_bus_config_commands",
    "build_bus_config_queries",
    "build_bus_protocol_queries",
    "bus_protocol_field_label",
    "bus_protocol_fields",
    "canonical_bus_type",
    "normalize_bus",
]
