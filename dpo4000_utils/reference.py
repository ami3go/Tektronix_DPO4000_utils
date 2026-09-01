"""Reference waveform support for Tektronix DPO4000-family oscilloscopes."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any

from .control import normalize_scope_response_text, quote_scpi_string, scpi_bool
from .errors import is_transport_error, transport_exception
from .io_policy import optional_query
from .scpi_values import format_scpi_number

REFERENCE_SLOTS = (1, 2, 3, 4)
REFERENCE_COUNT_QUERY = "CONFIGURATION:REFS:NUMREFS?"
REFERENCE_CAPABILITY_TIMEOUT_MS = 1000
REFERENCE_SOURCES = ("CH1", "CH2", "CH3", "CH4", "MATH", "REF1", "REF2", "REF3", "REF4")
REFERENCE_CONFIG_QUERIES = {
    "display": "SELECT:REF{reference}?",
    "label": "REF{reference}:LABEL?",
    "vertical_scale": "REF{reference}:VERTICAL:SCALE?",
    "vertical_position": "REF{reference}:VERTICAL:POSITION?",
    "horizontal_scale": "REF{reference}:HORIZONTAL:SCALE?",
    "horizontal_delay": "REF{reference}:HORIZONTAL:DELAY:TIME?",
    "date": "REF{reference}:DATE?",
    "time": "REF{reference}:TIME?",
}


@dataclass(frozen=True)
class ReferenceConfig:
    """Writable display configuration for one REF1..REF4 waveform."""

    reference: int
    display: bool | None = None
    label: str | None = None
    vertical_scale: str | float | int | None = None
    vertical_position: str | float | int | None = None
    horizontal_scale: str | float | int | None = None
    horizontal_delay: str | float | int | None = None


def normalize_reference(reference: int | str) -> int:
    """Validate and normalize a reference-memory number."""
    try:
        value = int(reference)
    except (TypeError, ValueError) as exc:
        raise ValueError("Reference waveform must be an integer from 1 to 4.") from exc
    if value not in REFERENCE_SLOTS:
        raise ValueError("Reference waveform must be between 1 and 4.")
    return value


def normalize_reference_source(source: str) -> str:
    """Normalize a waveform source accepted by SAVE:WAVEFORM."""
    token = str(source or "").strip().upper()
    if token == "MATH1":
        token = "MATH"
    if token not in REFERENCE_SOURCES:
        raise ValueError(f"Unsupported reference waveform source: {source!r}.")
    return token


def build_reference_config_queries(reference: int | str) -> dict[str, str]:
    """Build all readback queries for one reference waveform."""
    valid_reference = normalize_reference(reference)
    return {
        name: command.format(reference=valid_reference)
        for name, command in REFERENCE_CONFIG_QUERIES.items()
    }


def build_reference_config_commands(config: ReferenceConfig) -> list[str]:
    """Build validated SCPI writes for one reference waveform."""
    reference = normalize_reference(config.reference)
    commands: list[str] = []

    if config.label is not None:
        label = str(config.label)[:30]
        commands.append(f"REF{reference}:LABEL {quote_scpi_string(label)}")

    if config.vertical_scale is not None:
        scale = format_scpi_number(
            config.vertical_scale, field="Reference vertical scale", positive=True
        )
        commands.append(f"REF{reference}:VERTICAL:SCALE {scale}")
    if config.vertical_position is not None:
        commands.append(
            f"REF{reference}:VERTICAL:POSITION "
            f"{format_scpi_number(config.vertical_position, field='Reference vertical position')}"
        )
    if config.horizontal_scale is not None:
        scale = format_scpi_number(
            config.horizontal_scale, field="Reference horizontal scale", positive=True
        )
        commands.append(f"REF{reference}:HORIZONTAL:SCALE {scale}")
    if config.horizontal_delay is not None:
        commands.append(
            f"REF{reference}:HORIZONTAL:DELAY:TIME "
            f"{format_scpi_number(config.horizontal_delay, field='Reference horizontal delay')}"
        )

    if config.display is not None:
        commands.append(f"SELECT:REF{reference} {scpi_bool(config.display)}")

    return commands


def build_save_waveform_to_reference_command(source: str, reference: int | str) -> str:
    """Build a SAVE:WAVEFORM command that stores a waveform in REF memory."""
    valid_reference = normalize_reference(reference)
    waveform_source = normalize_reference_source(source)
    if waveform_source == f"REF{valid_reference}":
        raise ValueError("Source and destination reference waveform must be different.")
    return f"SAVE:WAVEFORM {waveform_source},REF{valid_reference}"


def _capability_timeout_context(driver: Any, timeout_ms: int):
    temporary_timeout = getattr(driver, "temporary_timeout", None)
    if callable(temporary_timeout):
        return temporary_timeout(timeout_ms)
    return nullcontext()


def _confirm_transport_alive(instrument: Any, failure: BaseException, operation: str) -> None:
    if not is_transport_error(failure):
        raise failure
    try:
        instrument.query("*IDN?")
    except Exception as health_exc:
        raise transport_exception(health_exc, f"{operation}; session health check") from health_exc


class ReferenceMixin:
    """Public high-level API for DPO4000 reference waveforms."""

    @staticmethod
    def _query_reference_optional(instrument: Any, command: str) -> str:
        return optional_query(instrument, command, normalizer=normalize_scope_response_text)

    def probe_reference_support(self, reference: int | str = 1) -> bool:
        """Probe one REF slot with a single required query."""
        valid_reference = normalize_reference(reference)
        scope = self.ensure_connected()
        query = build_reference_config_queries(valid_reference)["display"]
        response = normalize_scope_response_text(scope.query(query).strip())
        return bool(response)

    def get_reference_waveform_count(
        self,
        *,
        timeout_ms: int = REFERENCE_CAPABILITY_TIMEOUT_MS,
    ) -> int:
        """Return reference count with bounded older-firmware fallback."""
        instrument = self.ensure_connected()
        with _capability_timeout_context(self, timeout_ms):
            try:
                response = normalize_scope_response_text(
                    instrument.query(REFERENCE_COUNT_QUERY).strip()
                )
                count = int(float(response))
                return max(0, min(len(REFERENCE_SLOTS), count))
            except Exception as exc:
                _confirm_transport_alive(instrument, exc, "Reading reference waveform count")

            count = 0
            for reference in REFERENCE_SLOTS:
                query = build_reference_config_queries(reference)["display"]
                try:
                    response = normalize_scope_response_text(instrument.query(query).strip())
                except Exception as exc:
                    _confirm_transport_alive(instrument, exc, f"Probing REF{reference}")
                    break
                if not response:
                    break
                count = reference
            return count

    def get_available_reference_slots(
        self,
        *,
        timeout_ms: int = REFERENCE_CAPABILITY_TIMEOUT_MS,
    ) -> tuple[int, ...]:
        """Return actual reference slot numbers exposed by the connected scope."""
        return REFERENCE_SLOTS[: self.get_reference_waveform_count(timeout_ms=timeout_ms)]

    def get_reference_configuration(self, reference: int | str) -> dict[str, str]:
        """Read display parameters and storage metadata for one REF waveform."""
        scope = self.ensure_connected()
        return {
            name: self._query_reference_optional(scope, query)
            for name, query in build_reference_config_queries(reference).items()
        }

    def get_all_reference_configurations(self) -> dict[int, dict[str, str]]:
        """Read configurations only for reference slots exposed by the scope."""
        return {
            reference: self.get_reference_configuration(reference)
            for reference in self.get_available_reference_slots()
        }

    def configure_reference(self, config: ReferenceConfig) -> None:
        """Apply writable display properties to one reference waveform."""
        scope = self.ensure_connected()
        for command in build_reference_config_commands(config):
            scope.write(command)

    def save_waveform_to_reference(self, source: str, reference: int | str) -> None:
        """Store a live analog/MATH/other REF waveform into reference memory."""
        self.ensure_connected().write(build_save_waveform_to_reference_command(source, reference))


__all__ = [
    "REFERENCE_CAPABILITY_TIMEOUT_MS",
    "REFERENCE_CONFIG_QUERIES",
    "REFERENCE_COUNT_QUERY",
    "REFERENCE_SLOTS",
    "REFERENCE_SOURCES",
    "ReferenceConfig",
    "ReferenceMixin",
    "build_reference_config_commands",
    "build_reference_config_queries",
    "build_save_waveform_to_reference_command",
    "normalize_reference",
    "normalize_reference_source",
]
