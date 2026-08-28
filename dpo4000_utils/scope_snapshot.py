"""Read a complete GUI-facing oscilloscope state snapshot through public APIs."""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import nullcontext
from typing import Any

DEFAULT_ANALOG_CHANNELS = (1, 2, 3, 4)
DEFAULT_REFERENCE_CHANNELS = (1, 2, 3, 4)
DEFAULT_BUS_CHANNELS = (1, 2, 3, 4)
DEFAULT_OPTIONAL_FEATURE_TIMEOUT_MS = 1500


def _error_text(exc: BaseException) -> str:
    return str(exc).strip() or exc.__class__.__name__


def _optional_timeout_context(scope: Any, timeout_ms: int | None):
    """Return a driver-owned temporary-timeout context when available."""
    if timeout_ms is None:
        return nullcontext()
    temporary_timeout = getattr(scope, "temporary_timeout", None)
    if callable(temporary_timeout):
        return temporary_timeout(timeout_ms)
    return nullcontext()


def _optional_family_available(
    scope: Any,
    probe_name: str,
    first_slot: int,
    errors: dict[str, str],
    error_key: str,
    unavailable_text: str,
) -> bool:
    """Probe an optional feature family once before expanding into many queries."""
    probe = getattr(scope, probe_name, None)
    if not callable(probe):
        return True
    try:
        available = bool(probe(first_slot))
    except Exception as exc:  # noqa: BLE001 - optional feature discovery must be isolated.
        errors[error_key] = _error_text(exc)
        return False
    if not available:
        errors[error_key] = unavailable_text
        return False
    return True


def read_scope_snapshot(
    scope: Any,
    *,
    channels: Iterable[int] = DEFAULT_ANALOG_CHANNELS,
    references: Iterable[int] = DEFAULT_REFERENCE_CHANNELS,
    buses: Iterable[int] = DEFAULT_BUS_CHANNELS,
    optional_feature_timeout_ms: int | None = DEFAULT_OPTIONAL_FEATURE_TIMEOUT_MS,
) -> dict[str, Any]:
    """Read instrument-backed cards in one already-open driver session.

    Each logical section is isolated. Optional REF/BUS families are probed once
    under a bounded timeout before their detailed fields are read. This prevents
    an unsupported option from multiplying the full user-configured VISA timeout
    across dozens of queries.
    """
    channel_numbers = tuple(int(channel) for channel in channels)
    reference_numbers = tuple(int(reference) for reference in references)
    bus_numbers = tuple(int(bus) for bus in buses)
    errors: dict[str, str] = {}
    snapshot: dict[str, Any] = {
        "labels": {},
        "channels": {},
        "references": {},
        "buses": {},
        "math": {},
        "measurements": {},
        "trigger": {},
        "horizontal_position": None,
        "acquisition": {},
        "display": {},
        "errors": errors,
    }

    for channel in channel_numbers:
        try:
            snapshot["labels"][channel] = scope.get_channel_label(channel)
        except Exception as exc:  # noqa: BLE001 - one failed field must not abort refresh.
            errors[f"label.ch{channel}"] = _error_text(exc)

        try:
            snapshot["channels"][channel] = scope.get_channel_configuration(channel)
        except Exception as exc:  # noqa: BLE001 - isolate optional/firmware-specific reads.
            errors[f"channel.ch{channel}"] = _error_text(exc)

    reference_reader = getattr(scope, "get_reference_configuration", None)
    if callable(reference_reader) and reference_numbers:
        with _optional_timeout_context(scope, optional_feature_timeout_ms):
            if _optional_family_available(
                scope,
                "probe_reference_support",
                reference_numbers[0],
                errors,
                "reference.support",
                "Reference waveform controls are unavailable on this instrument.",
            ):
                for reference in reference_numbers:
                    try:
                        snapshot["references"][reference] = reference_reader(reference)
                    except Exception as exc:  # noqa: BLE001 - preserve other REF/scope sections.
                        errors[f"reference.ref{reference}"] = _error_text(exc)

    bus_reader = getattr(scope, "get_bus_configuration", None)
    if callable(bus_reader) and bus_numbers:
        with _optional_timeout_context(scope, optional_feature_timeout_ms):
            if _optional_family_available(
                scope,
                "probe_bus_support",
                bus_numbers[0],
                errors,
                "bus.support",
                "BUS waveform controls are unavailable or not licensed on this instrument.",
            ):
                for bus in bus_numbers:
                    try:
                        snapshot["buses"][bus] = bus_reader(bus)
                    except Exception as exc:  # noqa: BLE001 - one unsupported bus must not stop refresh.
                        errors[f"bus.bus{bus}"] = _error_text(exc)

    section_readers = (
        ("math", scope.get_math_configuration, {}),
        ("measurements", scope.get_all_measurement_setups, {}),
        ("trigger", scope.get_edge_trigger_configuration, {}),
        ("horizontal_position", scope.get_horizontal_position, None),
        ("acquisition", scope.get_acquisition_setup, {}),
        ("display", scope.get_display_settings, {}),
    )
    for name, reader, fallback in section_readers:
        try:
            snapshot[name] = reader()
        except Exception as exc:  # noqa: BLE001 - preserve all other successfully read cards.
            snapshot[name] = fallback
            errors[name] = _error_text(exc)

    return snapshot


__all__ = [
    "DEFAULT_ANALOG_CHANNELS",
    "DEFAULT_BUS_CHANNELS",
    "DEFAULT_OPTIONAL_FEATURE_TIMEOUT_MS",
    "DEFAULT_REFERENCE_CHANNELS",
    "read_scope_snapshot",
]
