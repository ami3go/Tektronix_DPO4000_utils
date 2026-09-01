"""Framework-neutral Logger scope producer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..waveform import WaveformRequest
from .models import LoggerConfig, LoggerMode, LoggerRecord, WaveformSnapshot


class BusDecodedEventsUnavailable(RuntimeError):
    """Decoded BUS extraction is not implemented/qualified by the connected driver."""


def capture_logger_record(scope: Any, config: LoggerConfig, sequence: int) -> LoggerRecord:
    """Capture one finite Logger record through public driver APIs only."""
    waveforms: list[WaveformSnapshot] = []
    if config.mode in {LoggerMode.WAVEFORM, LoggerMode.MIXED}:
        for source in config.waveform_sources:
            data = scope.read_waveform(
                WaveformRequest(
                    source=source,
                    point_count=config.point_count,
                    encoding=config.encoding,
                    sample_width=config.sample_width,
                )
            )
            waveforms.append(WaveformSnapshot.from_waveform(data))

    measurements: dict[int, float | None] = {}
    measurement_errors: dict[int, str] = {}
    if config.mode in {LoggerMode.MEASUREMENTS, LoggerMode.MIXED}:
        for slot in config.measurement_slots:
            try:
                raw = scope.read_measurement_value(slot)
                measurements[slot] = float(str(raw).strip().split()[-1])
            except Exception as exc:  # measurement read can fail independently of waveform record.
                from ..errors import is_transport_error

                if is_transport_error(exc):
                    raise
                measurements[slot] = None
                measurement_errors[slot] = str(exc)

    bus_events: dict[int, tuple[dict, ...]] = {}
    if config.mode in {LoggerMode.BUS, LoggerMode.MIXED} and config.bus_slots:
        reader = getattr(scope, "read_decoded_bus_events", None)
        if not callable(reader):
            raise BusDecodedEventsUnavailable(
                "Connected DPO4000 driver does not expose qualified decoded BUS event extraction."
            )
        for bus in config.bus_slots:
            events = reader(bus)
            bus_events[bus] = tuple(dict(event) for event in events)

    return LoggerRecord(
        sequence=int(sequence),
        captured_utc=datetime.now(timezone.utc).isoformat(),
        waveforms=tuple(waveforms),
        measurements=measurements,
        measurement_errors=measurement_errors,
        bus_events=bus_events,
    )


__all__ = ["BusDecodedEventsUnavailable", "capture_logger_record"]
