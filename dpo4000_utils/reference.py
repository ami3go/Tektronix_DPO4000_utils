"""Reference waveform support for Tektronix DPO4000-family oscilloscopes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .control import (
    normalize_optional_text,
    normalize_scope_response_text,
    quote_scpi_string,
    scpi_bool,
)

REFERENCE_SLOTS = (1, 2, 3, 4)
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
    """Build SCPI writes for the writable properties of one reference waveform."""
    reference = normalize_reference(config.reference)
    commands: list[str] = []

    if config.label is not None:
        label = str(config.label)[:30]
        commands.append(f"REF{reference}:LABEL {quote_scpi_string(label)}")

    for value, command in (
        (config.vertical_scale, f"REF{reference}:VERTICAL:SCALE"),
        (config.vertical_position, f"REF{reference}:VERTICAL:POSITION"),
        (config.horizontal_scale, f"REF{reference}:HORIZONTAL:SCALE"),
        (config.horizontal_delay, f"REF{reference}:HORIZONTAL:DELAY:TIME"),
    ):
        text = normalize_optional_text(value)
        if text:
            commands.append(f"{command} {text}")

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


class ReferenceMixin:
    """Public high-level API for DPO4000 reference waveforms."""

    @staticmethod
    def _query_reference_optional(instrument: Any, command: str) -> str:
        try:
            response = instrument.query(command).strip()
        except Exception:
            return ""
        return normalize_scope_response_text(response)

    def get_reference_configuration(self, reference: int | str) -> dict[str, str]:
        """Read display parameters and storage metadata for one REF waveform."""
        scope = self.ensure_connected()
        return {
            name: self._query_reference_optional(scope, query)
            for name, query in build_reference_config_queries(reference).items()
        }

    def get_all_reference_configurations(self) -> dict[int, dict[str, str]]:
        """Read REF1..REF4 configuration snapshots."""
        return {
            reference: self.get_reference_configuration(reference)
            for reference in REFERENCE_SLOTS
        }

    def configure_reference(self, config: ReferenceConfig) -> None:
        """Apply writable display properties to one reference waveform."""
        scope = self.ensure_connected()
        for command in build_reference_config_commands(config):
            scope.write(command)

    def save_waveform_to_reference(self, source: str, reference: int | str) -> None:
        """Store a live analog/MATH/other REF waveform into reference memory."""
        self.ensure_connected().write(
            build_save_waveform_to_reference_command(source, reference)
        )


__all__ = [
    "REFERENCE_CONFIG_QUERIES",
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
