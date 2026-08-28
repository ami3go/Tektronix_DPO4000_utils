"""Read a complete GUI-facing oscilloscope state snapshot through public APIs."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

DEFAULT_ANALOG_CHANNELS = (1, 2, 3, 4)


def _error_text(exc: BaseException) -> str:
    return str(exc).strip() or exc.__class__.__name__


def read_scope_snapshot(
    scope: Any,
    *,
    channels: Iterable[int] = DEFAULT_ANALOG_CHANNELS,
) -> dict[str, Any]:
    """Read instrument-backed cards in one already-open driver session.

    Each logical section is isolated.  A rejected optional query is recorded in
    ``errors`` while the remaining cards continue to load.
    """
    channel_numbers = tuple(int(channel) for channel in channels)
    errors: dict[str, str] = {}
    snapshot: dict[str, Any] = {
        "labels": {},
        "channels": {},
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


__all__ = ["DEFAULT_ANALOG_CHANNELS", "read_scope_snapshot"]
