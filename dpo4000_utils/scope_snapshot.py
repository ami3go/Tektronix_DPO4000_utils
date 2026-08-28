"""Bounded, staged GUI-facing oscilloscope state snapshot reads.

Capability discovery is owned by the public BUS/REF driver APIs. This module only
orchestrates staged reads and never carries an independent Tektronix slot-count
implementation.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import nullcontext
from typing import Any

from .bus import (
    BUS_COUNT_QUERY,
    build_bus_config_queries,
    build_bus_protocol_queries,
    canonical_bus_type,
)
from .control import normalize_scope_response_text
from .errors import DPOTransportError, is_transport_error, transport_exception
from .reference import REFERENCE_COUNT_QUERY, build_reference_config_queries

DEFAULT_ANALOG_CHANNELS = (1, 2, 3, 4)
DEFAULT_REFERENCE_CHANNELS = (1, 2, 3, 4)
DEFAULT_BUS_CHANNELS = (1, 2, 3, 4)
DEFAULT_OPTIONAL_FEATURE_TIMEOUT_MS = 1000


def _error_text(exc: BaseException) -> str:
    return str(exc).strip() or exc.__class__.__name__


def _raise_transport_if_typed(exc: BaseException) -> None:
    if isinstance(exc, DPOTransportError):
        raise exc


def _empty_snapshot() -> dict[str, Any]:
    return {
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
        "capabilities": {},
        "errors": {},
    }


def merge_scope_snapshots(*snapshots: Mapping[str, Any]) -> dict[str, Any]:
    """Merge staged snapshot fragments without clearing earlier successful reads."""
    merged = _empty_snapshot()
    dict_sections = {
        "labels",
        "channels",
        "references",
        "buses",
        "math",
        "measurements",
        "trigger",
        "acquisition",
        "display",
        "capabilities",
        "errors",
    }
    for snapshot in snapshots:
        if not isinstance(snapshot, Mapping):
            continue
        for name in dict_sections:
            value = snapshot.get(name)
            if isinstance(value, Mapping):
                merged[name].update(value)
        if "horizontal_position" in snapshot and snapshot.get("horizontal_position") is not None:
            merged["horizontal_position"] = snapshot.get("horizontal_position")
    return merged


def _optional_timeout_context(scope: Any, timeout_ms: int | None):
    if timeout_ms is None:
        return nullcontext()
    temporary_timeout = getattr(scope, "temporary_timeout", None)
    if callable(temporary_timeout):
        return temporary_timeout(timeout_ms)
    return nullcontext()


def _scope_bool(value: object) -> bool:
    return str(value or "").strip().upper() in {"1", "ON", "TRUE", "YES"}


def _instrument_for_snapshot(scope: Any) -> Any | None:
    ensure_connected = getattr(scope, "ensure_connected", None)
    if not callable(ensure_connected):
        return None
    try:
        instrument = ensure_connected()
    except Exception:
        return None
    return instrument if callable(getattr(instrument, "query", None)) else None


def _query_normalized(instrument: Any, command: str) -> str:
    return normalize_scope_response_text(instrument.query(command).strip())


def _requested_available_slots(
    scope: Any,
    requested: tuple[int, ...],
    *,
    available_method: str,
    count_key: str,
    snapshot: dict[str, Any],
    timeout_ms: int | None,
) -> tuple[int, ...]:
    """Intersect caller-requested slots with the public driver capability API."""
    reader = getattr(scope, available_method, None)
    if not callable(reader):
        return requested
    kwargs = {} if timeout_ms is None else {"timeout_ms": timeout_ms}
    available = tuple(int(slot) for slot in reader(**kwargs))
    snapshot["capabilities"][count_key] = len(available)
    available_set = set(available)
    return tuple(slot for slot in requested if slot in available_set)


def read_core_scope_snapshot(
    scope: Any,
    *,
    channels: Iterable[int] = DEFAULT_ANALOG_CHANNELS,
) -> dict[str, Any]:
    """Read mandatory/common scope state first, with no BUS/REF traffic."""
    snapshot = _empty_snapshot()
    errors = snapshot["errors"]

    for channel in tuple(int(channel) for channel in channels):
        try:
            snapshot["labels"][channel] = scope.get_channel_label(channel)
        except Exception as exc:  # noqa: BLE001
            _raise_transport_if_typed(exc)
            errors[f"label.ch{channel}"] = _error_text(exc)
        try:
            snapshot["channels"][channel] = scope.get_channel_configuration(channel)
        except Exception as exc:  # noqa: BLE001
            _raise_transport_if_typed(exc)
            errors[f"channel.ch{channel}"] = _error_text(exc)

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
        except Exception as exc:  # noqa: BLE001
            _raise_transport_if_typed(exc)
            snapshot[name] = fallback
            errors[name] = _error_text(exc)
    return snapshot


def _read_reference_direct(
    scope: Any,
    references: tuple[int, ...],
    timeout_ms: int | None,
) -> dict[str, Any] | None:
    instrument = _instrument_for_snapshot(scope)
    if instrument is None:
        return None

    snapshot = _empty_snapshot()
    errors = snapshot["errors"]
    if not references:
        return snapshot

    active_references = _requested_available_slots(
        scope,
        references,
        available_method="get_available_reference_slots",
        count_key="reference_count",
        snapshot=snapshot,
        timeout_ms=timeout_ms,
    )

    with _optional_timeout_context(scope, timeout_ms):
        for reference in active_references:
            queries = build_reference_config_queries(reference)
            values: dict[str, str] = {}
            try:
                values["display"] = _query_normalized(instrument, queries["display"])
            except Exception as exc:  # noqa: BLE001
                if is_transport_error(exc):
                    raise transport_exception(exc, f"Reading REF{reference} display") from exc
                errors[f"reference.ref{reference}"] = _error_text(exc)
                continue

            for name, query in queries.items():
                if name == "display":
                    continue
                try:
                    values[name] = _query_normalized(instrument, query)
                except Exception as exc:  # noqa: BLE001
                    errors[f"reference.ref{reference}.{name}"] = _error_text(exc)
                    break
            snapshot["references"][reference] = values
    return snapshot


def read_reference_scope_snapshot(
    scope: Any,
    *,
    references: Iterable[int] = DEFAULT_REFERENCE_CHANNELS,
    optional_feature_timeout_ms: int | None = DEFAULT_OPTIONAL_FEATURE_TIMEOUT_MS,
) -> dict[str, Any]:
    """Read reference-waveform slots exposed by the connected scope."""
    reference_numbers = tuple(int(reference) for reference in references)
    direct = _read_reference_direct(scope, reference_numbers, optional_feature_timeout_ms)
    if direct is not None:
        return direct

    snapshot = _empty_snapshot()
    errors = snapshot["errors"]
    reader = getattr(scope, "get_reference_configuration", None)
    if not callable(reader):
        return snapshot

    reference_numbers = _requested_available_slots(
        scope,
        reference_numbers,
        available_method="get_available_reference_slots",
        count_key="reference_count",
        snapshot=snapshot,
        timeout_ms=optional_feature_timeout_ms,
    )
    with _optional_timeout_context(scope, optional_feature_timeout_ms):
        probe = getattr(scope, "probe_reference_support", None)
        if callable(probe) and reference_numbers:
            try:
                if not probe(reference_numbers[0]):
                    errors["reference.support"] = "Reference waveform controls are unavailable."
                    return snapshot
            except Exception as exc:  # noqa: BLE001
                _raise_transport_if_typed(exc)
                errors["reference.support"] = _error_text(exc)
                return snapshot
        for reference in reference_numbers:
            try:
                snapshot["references"][reference] = reader(reference)
            except Exception as exc:  # noqa: BLE001
                _raise_transport_if_typed(exc)
                errors[f"reference.ref{reference}"] = _error_text(exc)
    return snapshot


def _read_bus_direct(
    scope: Any,
    buses: tuple[int, ...],
    timeout_ms: int | None,
) -> dict[str, Any] | None:
    instrument = _instrument_for_snapshot(scope)
    if instrument is None:
        return None

    snapshot = _empty_snapshot()
    errors = snapshot["errors"]
    if not buses:
        return snapshot

    active_buses = _requested_available_slots(
        scope,
        buses,
        available_method="get_available_bus_slots",
        count_key="bus_count",
        snapshot=snapshot,
        timeout_ms=timeout_ms,
    )

    with _optional_timeout_context(scope, timeout_ms):
        for bus in active_buses:
            queries = build_bus_config_queries(bus)
            values: dict[str, Any] = {"protocol": {}}
            required_failed = False
            for name in ("state", "type"):
                try:
                    values[name] = _query_normalized(instrument, queries[name])
                except Exception as exc:  # noqa: BLE001
                    if is_transport_error(exc):
                        raise transport_exception(exc, f"Reading BUS{bus} {name}") from exc
                    errors[f"bus.bus{bus}.{name}"] = _error_text(exc)
                    required_failed = True
                    break
            if required_failed:
                continue

            values["type"] = canonical_bus_type(values.get("type", ""))
            for name in ("label", "position", "display_format", "display_type"):
                try:
                    values[name] = _query_normalized(instrument, queries[name])
                except Exception as exc:  # noqa: BLE001
                    errors[f"bus.bus{bus}.{name}"] = _error_text(exc)
                    break

            if _scope_bool(values.get("state")) and values.get("type"):
                protocol_values: dict[str, str] = {}
                for name, query in build_bus_protocol_queries(bus, values["type"]).items():
                    try:
                        protocol_values[name] = _query_normalized(instrument, query)
                    except Exception as exc:  # noqa: BLE001
                        errors[f"bus.bus{bus}.protocol.{name}"] = _error_text(exc)
                        break
                values["protocol"] = protocol_values

            snapshot["buses"][bus] = values
    return snapshot


def read_bus_scope_snapshot(
    scope: Any,
    *,
    buses: Iterable[int] = DEFAULT_BUS_CHANNELS,
    optional_feature_timeout_ms: int | None = DEFAULT_OPTIONAL_FEATURE_TIMEOUT_MS,
) -> dict[str, Any]:
    """Read only BUS waveforms that the public driver API reports as present."""
    bus_numbers = tuple(int(bus) for bus in buses)
    direct = _read_bus_direct(scope, bus_numbers, optional_feature_timeout_ms)
    if direct is not None:
        return direct

    snapshot = _empty_snapshot()
    errors = snapshot["errors"]
    reader = getattr(scope, "get_bus_configuration", None)
    if not callable(reader):
        return snapshot

    bus_numbers = _requested_available_slots(
        scope,
        bus_numbers,
        available_method="get_available_bus_slots",
        count_key="bus_count",
        snapshot=snapshot,
        timeout_ms=optional_feature_timeout_ms,
    )
    with _optional_timeout_context(scope, optional_feature_timeout_ms):
        probe = getattr(scope, "probe_bus_support", None)
        if callable(probe) and bus_numbers:
            try:
                if not probe(bus_numbers[0]):
                    errors["bus.support"] = "BUS waveform controls are unavailable or not licensed."
                    return snapshot
            except Exception as exc:  # noqa: BLE001
                _raise_transport_if_typed(exc)
                errors["bus.support"] = _error_text(exc)
                return snapshot
        for bus in bus_numbers:
            try:
                snapshot["buses"][bus] = reader(bus)
            except Exception as exc:  # noqa: BLE001
                _raise_transport_if_typed(exc)
                errors[f"bus.bus{bus}"] = _error_text(exc)
    return snapshot


def read_scope_snapshot(
    scope: Any,
    *,
    channels: Iterable[int] = DEFAULT_ANALOG_CHANNELS,
    references: Iterable[int] = DEFAULT_REFERENCE_CHANNELS,
    buses: Iterable[int] = DEFAULT_BUS_CHANNELS,
    optional_feature_timeout_ms: int | None = DEFAULT_OPTIONAL_FEATURE_TIMEOUT_MS,
) -> dict[str, Any]:
    """Compatibility one-call snapshot composed from the staged read plan."""
    return merge_scope_snapshots(
        read_core_scope_snapshot(scope, channels=channels),
        read_reference_scope_snapshot(
            scope,
            references=references,
            optional_feature_timeout_ms=optional_feature_timeout_ms,
        ),
        read_bus_scope_snapshot(
            scope,
            buses=buses,
            optional_feature_timeout_ms=optional_feature_timeout_ms,
        ),
    )


__all__ = [
    "BUS_COUNT_QUERY",
    "DEFAULT_ANALOG_CHANNELS",
    "DEFAULT_BUS_CHANNELS",
    "DEFAULT_OPTIONAL_FEATURE_TIMEOUT_MS",
    "DEFAULT_REFERENCE_CHANNELS",
    "REFERENCE_COUNT_QUERY",
    "merge_scope_snapshots",
    "read_bus_scope_snapshot",
    "read_core_scope_snapshot",
    "read_reference_scope_snapshot",
    "read_scope_snapshot",
]
