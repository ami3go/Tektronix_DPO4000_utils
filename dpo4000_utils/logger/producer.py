"""Framework-neutral Logger scope producer."""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any

from ..automation.triggered import wait_for_fresh_single
from ..errors import is_transport_error
from ..waveform import WaveformRequest
from .models import LoggerConfig, LoggerMode, LoggerRecord, WaveformSnapshot


class BusDecodedEventsUnavailable(RuntimeError):
    """Decoded BUS extraction is unavailable or not hardware-qualified."""


class LoggerCaptureCancelled(RuntimeError):
    """A cancellable mixed Single acquisition was stopped by the operator."""


def _measurement_value(scope: Any, slot: int) -> float:
    raw = scope.read_measurement_value(slot)
    value = float(str(raw).strip().split()[-1])
    if not math.isfinite(value) or abs(value) >= 9.0e36:
        raise ValueError(f"MEAS{slot} returned an unavailable/overflow value: {raw!r}")
    return value


def _event_dict(event: Any) -> dict[str, Any]:
    if isinstance(event, dict):
        return dict(event)
    converter = getattr(event, "to_dict", None)
    if callable(converter):
        value = converter()
        if isinstance(value, dict):
            return dict(value)
    raise TypeError(
        "Decoded BUS event must be a mapping or expose to_dict(), "
        f"got {type(event).__name__}."
    )


def _wait_mixed_single(scope: Any, cancel_event=None, timeout_s: float = 30.0) -> str:
    wait = wait_for_fresh_single(
        scope,
        cancel_event,
        poll_interval_s=0.1,
        timeout_s=timeout_s,
    )
    if wait.cancelled:
        raise LoggerCaptureCancelled("Mixed Logger acquisition cancelled.")
    if wait.timed_out:
        raise TimeoutError(
            f"Mixed Logger Single acquisition did not complete within {timeout_s:g} s "
            "after observing a fresh active/armed state."
        )
    if not wait.completed:
        raise RuntimeError("Mixed Logger Single acquisition ended without a verified fresh completion.")
    return wait.trigger_state


def capture_logger_record(
    scope: Any,
    config: LoggerConfig,
    sequence: int,
    *,
    cancel_event=None,
) -> LoggerRecord:
    """Capture one Logger record through public driver APIs only."""
    metadata: dict[str, Any] = {
        "acquisition_id": int(sequence),
        "partial": False,
    }
    if config.mode is LoggerMode.MIXED:
        metadata["trigger_state"] = _wait_mixed_single(scope, cancel_event)
        metadata["acquisition_policy"] = "fresh-single-complete-before-read"

    # Timestamp at the producer/acquisition boundary, before potentially slow
    # waveform/BUS transfers and before the record enters the writer queue.
    captured_monotonic = time.monotonic()
    captured_utc = datetime.now(timezone.utc).isoformat()

    waveforms: list[WaveformSnapshot] = []
    waveform_errors: dict[str, str] = {}
    if config.mode in {LoggerMode.WAVEFORM, LoggerMode.MIXED}:
        for source in config.waveform_sources:
            try:
                data = scope.read_waveform(
                    WaveformRequest(
                        source=source,
                        point_count=config.point_count,
                        encoding=config.encoding,
                        sample_width=config.sample_width,
                    )
                )
                waveforms.append(WaveformSnapshot.from_waveform(data))
            except Exception as exc:  # noqa: BLE001 - component failures may be partial.
                if is_transport_error(exc) or config.mode is LoggerMode.WAVEFORM:
                    raise
                waveform_errors[source] = str(exc)
                metadata["partial"] = True
    if waveform_errors:
        metadata["waveform_errors"] = waveform_errors

    measurements: dict[int, float | None] = {}
    measurement_errors: dict[int, str] = {}
    if config.mode in {LoggerMode.MEASUREMENTS, LoggerMode.MIXED}:
        for slot in config.measurement_slots:
            try:
                measurements[slot] = _measurement_value(scope, slot)
            except Exception as exc:  # noqa: BLE001 - one measurement may be unavailable.
                if is_transport_error(exc):
                    raise
                measurements[slot] = None
                measurement_errors[slot] = str(exc)
                metadata["partial"] = True

    bus_events: dict[int, tuple[dict[str, Any], ...]] = {}
    if config.mode in {LoggerMode.BUS, LoggerMode.MIXED} and config.bus_slots:
        supports = getattr(scope, "supports_decoded_bus_events", None)
        if callable(supports) and not bool(supports()):
            raise BusDecodedEventsUnavailable(
                "Connected DPO4000 driver reports decoded BUS event extraction as "
                "unavailable/unqualified."
            )
        reader = getattr(scope, "read_decoded_bus_events", None)
        if not callable(reader):
            raise BusDecodedEventsUnavailable(
                "Connected DPO4000 driver does not expose qualified decoded BUS event extraction."
            )
        for bus in config.bus_slots:
            bus_events[bus] = tuple(_event_dict(event) for event in reader(bus))

    return LoggerRecord(
        sequence=int(sequence),
        captured_utc=captured_utc,
        captured_monotonic=captured_monotonic,
        waveforms=tuple(waveforms),
        measurements=measurements,
        measurement_errors=measurement_errors,
        bus_events=bus_events,
        metadata=metadata,
    )


__all__ = [
    "BusDecodedEventsUnavailable",
    "LoggerCaptureCancelled",
    "capture_logger_record",
]
