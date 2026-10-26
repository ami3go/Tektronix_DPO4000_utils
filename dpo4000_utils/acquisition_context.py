"""Read-only acquisition context for exports and evidence.

Collects acquisition, timebase and enabled-measurement readbacks through public
driver methods so exported data records the conditions it was captured under.
Transport failures propagate; an individual unsupported or malformed readback is
recorded in ``errors`` instead of aborting the export.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import math
from typing import Any, Callable

from .errors import is_transport_error

ACQUISITION_CONTEXT_VERSION = 1
_ENABLED_STATES = {"1", "ON"}


def _numeric(value: Any) -> float | None:
    tokens = str(value or "").strip().split()
    if not tokens:
        return None
    try:
        number = float(tokens[-1])
    except ValueError:
        return None
    # The DPO4000 reports 9.91E37 for an invalid/undefined measurement.
    if not math.isfinite(number) or abs(number) >= 9.9e37:
        return None
    return number


def _read(name: str, reader: Callable[[], Any], errors: dict[str, str]) -> Any:
    try:
        return reader()
    except Exception as exc:  # noqa: BLE001 - classify transport vs optional readback failure.
        if is_transport_error(exc):
            raise
        errors[name] = f"{type(exc).__name__}: {exc}"
        return None


def _finite(name: str, value: Any, errors: dict[str, str]) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors[name] = f"non-numeric readback {value!r}"
        return None
    if not math.isfinite(number):
        errors[name] = f"non-finite readback {value!r}"
        return None
    return number


def _measurements(scope: Any, errors: dict[str, str]) -> list[dict[str, Any]]:
    setups = _read("measurements", scope.get_all_measurement_setups, errors)
    if not isinstance(setups, dict):
        return []
    unit_reader = getattr(scope, "read_measurement_unit", None)
    items: list[dict[str, Any]] = []
    for slot in sorted(setups):
        setup = setups[slot]
        data = asdict(setup) if is_dataclass(setup) and not isinstance(setup, type) else dict(setup)
        if str(data.get("state", "")).strip().upper() not in _ENABLED_STATES:
            continue
        unit = None
        if unit_reader is not None:
            unit = _read(f"MEAS{slot}.unit", lambda slot=slot: unit_reader(slot), errors)
        items.append(
            {
                "slot": int(data.get("slot", slot)),
                "type": str(data.get("measurement_type", "")),
                "source1": str(data.get("source1", "")),
                "source2": str(data.get("source2", "")),
                "value_text": str(data.get("value", "")),
                "value": _numeric(data.get("value")),
                "unit": unit or None,
            }
        )
    return items


def read_acquisition_context(scope: Any, *, include_measurements: bool = True) -> dict[str, Any]:
    """Return a JSON-compatible snapshot of acquisition settings and enabled measurements."""
    errors: dict[str, str] = {}
    acquisition = _read("acquisition", scope.get_acquisition_setup, errors)
    context: dict[str, Any] = {
        "version": ACQUISITION_CONTEXT_VERSION,
        "acquisition": {str(key): str(value) for key, value in dict(acquisition or {}).items()},
        "horizontal_scale_s_per_div": _finite(
            "horizontal_scale",
            _read("horizontal_scale", scope.get_horizontal_scale, errors),
            errors,
        ),
        "horizontal_position": _finite(
            "horizontal_position",
            _read("horizontal_position", scope.get_horizontal_position, errors),
            errors,
        ),
        "record_length": _read("record_length", scope.get_record_length, errors),
    }
    if include_measurements:
        context["measurements"] = _measurements(scope, errors)
    context["errors"] = errors
    return context


__all__ = ["ACQUISITION_CONTEXT_VERSION", "read_acquisition_context"]
