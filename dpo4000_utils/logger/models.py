"""Framework-neutral Logger data models."""

from __future__ import annotations

import math
import sys
from array import array
from dataclasses import dataclass, field
from datetime import timezone
from enum import Enum
from typing import Any, Mapping

from ..waveform import WaveformData, normalize_waveform_source


class LoggerState(str, Enum):
    IDLE = "Idle"
    RUNNING = "Running"
    PAUSED = "Paused"
    FAILED = "Failed"


class LoggerMode(str, Enum):
    WAVEFORM = "Waveform records"
    MEASUREMENTS = "Measurements"
    BUS = "BUS decoded events"
    MIXED = "Mixed record"


class LoggerOutputFormat(str, Enum):
    CSV = "CSV"
    BINARY = "Binary DPO4LOG"
    BOTH = "CSV + Binary"


@dataclass(frozen=True)
class WaveformSnapshot:
    source: str
    label: str
    start_index: int
    stop_index: int
    acquired_utc: str
    typecode: str
    sample_bytes: bytes
    sample_count: int
    byte_order: str
    preamble: Mapping[str, Any]

    @classmethod
    def from_waveform(cls, waveform: WaveformData) -> "WaveformSnapshot":
        preamble = waveform.preamble
        return cls(
            source=waveform.source,
            label=waveform.label,
            start_index=waveform.start_index,
            stop_index=waveform.stop_index,
            acquired_utc=waveform.acquired_at.astimezone(timezone.utc).isoformat(),
            typecode=waveform.samples.typecode,
            sample_bytes=waveform.samples.tobytes(),
            sample_count=waveform.sample_count,
            byte_order=sys.byteorder,
            preamble={
                "byte_width": preamble.byte_width,
                "encoding": preamble.encoding,
                "binary_format": preamble.binary_format,
                "byte_order": preamble.byte_order,
                "record_point_count": preamble.record_point_count,
                "point_format": preamble.point_format,
                "x_unit": preamble.x_unit,
                "x_increment": preamble.x_increment,
                "x_zero": preamble.x_zero,
                "point_offset": preamble.point_offset,
                "y_unit": preamble.y_unit,
                "y_multiplier": preamble.y_multiplier,
                "y_offset": preamble.y_offset,
                "y_zero": preamble.y_zero,
            },
        )

    def samples(self) -> array:
        values = array(self.typecode)
        values.frombytes(self.sample_bytes)
        stored_order = str(self.byte_order).lower()
        if values.itemsize > 1 and stored_order in {"little", "big"} and stored_order != sys.byteorder:
            values.byteswap()
        if len(values) != self.sample_count:
            raise ValueError(
                f"Waveform snapshot sample count mismatch: metadata={self.sample_count}, bytes={len(values)}."
            )
        return values

    def time_at(self, index: int) -> float:
        if index < 0 or index >= self.sample_count:
            raise IndexError(index)
        return float(self.preamble["x_zero"]) + float(self.preamble["x_increment"]) * (
            index - float(self.preamble["point_offset"])
        )

    def value_at(self, index: int) -> float:
        raw = self.samples()[index]
        return (
            (raw - float(self.preamble["y_offset"])) * float(self.preamble["y_multiplier"])
            + float(self.preamble["y_zero"])
        )

    @property
    def estimated_bytes(self) -> int:
        return len(self.sample_bytes) + 512


@dataclass(frozen=True)
class LoggerRecord:
    sequence: int
    captured_utc: str
    waveforms: tuple[WaveformSnapshot, ...] = ()
    measurements: Mapping[int, float | None] = field(default_factory=dict)
    measurement_errors: Mapping[int, str] = field(default_factory=dict)
    bus_events: Mapping[int, tuple[Mapping[str, Any], ...]] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def estimated_bytes(self) -> int:
        waveform_bytes = sum(waveform.estimated_bytes for waveform in self.waveforms)
        return waveform_bytes + 1024 + len(self.measurements) * 32 + sum(
            len(events) * 256 for events in self.bus_events.values()
        )


@dataclass(frozen=True)
class LoggerConfig:
    mode: LoggerMode = LoggerMode.WAVEFORM
    interval_s: float = 1.0
    waveform_sources: tuple[str, ...] = ("CH1",)
    measurement_slots: tuple[int, ...] = ()
    bus_slots: tuple[int, ...] = ()
    encoding: str = "RIBINARY"
    sample_width: int = 2
    point_count: int | None = None

    def __post_init__(self) -> None:
        mode = LoggerMode(self.mode)
        interval = float(self.interval_s)
        if not math.isfinite(interval) or interval < 0.1 or interval > 7 * 24 * 3600:
            raise ValueError("Logger interval must be between 0.1 seconds and 7 days.")
        sources: list[str] = []
        for source in self.waveform_sources:
            normalized = normalize_waveform_source(source)
            if normalized not in sources:
                sources.append(normalized)
        slots: list[int] = []
        for raw in self.measurement_slots:
            if isinstance(raw, bool):
                raise ValueError("Measurement slots must be integers from 1 to 8.")
            slot = int(raw)
            if slot not in range(1, 9):
                raise ValueError("Measurement slots must be between 1 and 8.")
            if slot not in slots:
                slots.append(slot)
        buses: list[int] = []
        for raw in self.bus_slots:
            if isinstance(raw, bool):
                raise ValueError("BUS slots must be integers from 1 to 4.")
            bus = int(raw)
            if bus not in range(1, 5):
                raise ValueError("BUS slots must be between 1 and 4.")
            if bus not in buses:
                buses.append(bus)
        if mode is LoggerMode.WAVEFORM and not sources:
            raise ValueError("Waveform Logger requires at least one waveform source.")
        if mode is LoggerMode.MEASUREMENTS and not slots:
            raise ValueError("Measurement Logger requires at least one MEAS slot.")
        if mode is LoggerMode.BUS and not buses:
            raise ValueError("BUS Logger requires at least one BUS slot.")
        if mode is LoggerMode.MIXED and not (sources or slots or buses):
            raise ValueError("Mixed Logger requires at least one source.")
        point_count = self.point_count
        if point_count is not None:
            if isinstance(point_count, bool) or int(point_count) < 1:
                raise ValueError("Logger point count must be a positive integer or None.")
            point_count = int(point_count)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "interval_s", interval)
        object.__setattr__(self, "waveform_sources", tuple(sources))
        object.__setattr__(self, "measurement_slots", tuple(slots))
        object.__setattr__(self, "bus_slots", tuple(buses))
        object.__setattr__(self, "point_count", point_count)


@dataclass
class LoggerStatistics:
    records_captured: int = 0
    records_written: int = 0
    skipped: int = 0
    failed: int = 0
    bytes_written: int = 0
    last_error: str = ""
    started_monotonic: float | None = None


__all__ = [
    "LoggerConfig",
    "LoggerMode",
    "LoggerOutputFormat",
    "LoggerRecord",
    "LoggerState",
    "LoggerStatistics",
    "WaveformSnapshot",
]
