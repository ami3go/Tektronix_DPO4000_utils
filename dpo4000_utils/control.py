"""Display measurement, horizontal, and trigger control helpers."""

from __future__ import annotations

from dataclasses import dataclass


MEASUREMENT_SLOTS = tuple(range(1, 9))
MEASUREMENT_SOURCES = ("CH1", "CH2", "CH3", "CH4", "MATH", "REF1", "REF2", "REF3", "REF4")
MEASUREMENT_TYPES_BY_GROUP: dict[str, tuple[str, ...]] = {
    "Amplitude": (
        "AMPLITUDE",
        "MAXIMUM",
        "MINIMUM",
        "MEAN",
        "PK2PK",
        "RMS",
        "CRMS",
        "HIGH",
        "LOW",
        "OVERSHOOT",
        "UNDERSHOOT",
    ),
    "Timing": (
        "FREQUENCY",
        "PERIOD",
        "RISE",
        "FALL",
        "PWIDTH",
        "NWIDTH",
        "PDUTY",
        "NDUTY",
        "DELAY",
        "PHASE",
    ),
    "Area / count": (
        "AREA",
        "CAREA",
        "CYCLES",
        "PULSES",
        "EDGES",
    ),
}
MEASUREMENT_TYPES = tuple(item for group in MEASUREMENT_TYPES_BY_GROUP.values() for item in group)

TRIGGER_TYPES = ("EDGE", "PULSE", "RUNT", "TIMEOUT", "LOGIC", "VIDEO")
TRIGGER_MODES = ("AUTO", "NORMAL")
TRIGGER_SOURCES = ("CH1", "CH2", "CH3", "CH4", "AUX", "LINE")
TRIGGER_SLOPES = ("RISE", "FALL", "EITHER")
TRIGGER_COUPLINGS = ("DC", "AC", "HFREJ", "LFREJ", "NOISEREJ")
FORCE_TRIGGER_COMMAND = "TRIG FORC"

RECORD_LENGTH_LABELS = (
    "1k",
    "10k",
    "100k",
    "1M",
    "10M",
)
RECORD_LENGTH_POINTS_BY_LABEL = {
    "1K": 1_000,
    "10K": 10_000,
    "100K": 100_000,
    "1M": 1_000_000,
    "10M": 10_000_000,
}
RECORD_LENGTH_LABEL_BY_POINTS = {
    points: label for label, points in zip(RECORD_LENGTH_LABELS, RECORD_LENGTH_POINTS_BY_LABEL.values())
}


@dataclass(frozen=True)
class MeasurementConfig:
    """One displayed measurement slot configuration."""

    slot: int
    measurement_type: str
    source1: str = "CH1"
    source2: str | None = None


def _normalize_token(value: str, *, field: str) -> str:
    token = str(value or "").strip().upper()
    if not token:
        raise ValueError(f"{field} cannot be empty.")
    return token


def validate_measurement_slot(slot: int) -> int:
    try:
        value = int(slot)
    except (TypeError, ValueError) as exc:
        raise ValueError("Measurement slot must be an integer from 1 to 8.") from exc
    if value not in MEASUREMENT_SLOTS:
        raise ValueError("Measurement slot must be between 1 and 8.")
    return value


def normalize_source(source: str, *, field: str = "Source") -> str:
    token = _normalize_token(source, field=field)
    if token not in MEASUREMENT_SOURCES and token not in TRIGGER_SOURCES:
        raise ValueError(f"Unsupported {field.lower()}: {source!r}.")
    return token


def normalize_measurement_type(measurement_type: str) -> str:
    return _normalize_token(measurement_type, field="Measurement type")


def normalize_trigger_choice(value: str, allowed: tuple[str, ...], *, field: str) -> str:
    token = _normalize_token(value, field=field)
    if token not in allowed:
        raise ValueError(f"Unsupported {field.lower()}: {value!r}.")
    return token


def build_measurement_commands(config: MeasurementConfig) -> list[str]:
    """Build SCPI commands that add/update one displayed measurement slot."""
    slot = validate_measurement_slot(config.slot)
    measurement_type = normalize_measurement_type(config.measurement_type)
    source1 = normalize_source(config.source1, field="Source 1")
    source2 = normalize_source(config.source2, field="Source 2") if config.source2 else None

    commands = [
        f"MEASUREMENT:MEAS{slot}:TYPE {measurement_type}",
        f"MEASUREMENT:MEAS{slot}:SOURCE1 {source1}",
    ]
    if source2:
        commands.append(f"MEASUREMENT:MEAS{slot}:SOURCE2 {source2}")
    commands.append(f"MEASUREMENT:MEAS{slot}:STATE ON")
    return commands


def build_disable_measurement_command(slot: int) -> str:
    return f"MEASUREMENT:MEAS{validate_measurement_slot(slot)}:STATE OFF"


def build_measurement_value_query(slot: int) -> str:
    return f"MEASUREMENT:MEAS{validate_measurement_slot(slot)}:VALUE?"


def normalize_horizontal_position(value: str | float | int) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Horizontal position must be a numeric value.") from exc


def build_horizontal_position_command(position: str | float | int) -> str:
    return f"HORIZONTAL:POSITION {normalize_horizontal_position(position):g}"


def build_horizontal_position_query() -> str:
    return "HORIZONTAL:POSITION?"


def normalize_record_length(record_length: str | float | int) -> int:
    """Normalize a record-length setting to an integer point count.

    Friendly labels such as ``1k`` and ``1M`` are accepted, but arbitrary
    positive integer point counts are intentionally also allowed because exact
    valid values can vary by DPO4000 model, option set, and acquisition mode.
    """
    if isinstance(record_length, bool):
        raise ValueError("Record length must be a positive integer point count or label.")

    if isinstance(record_length, str):
        text = record_length.strip()
        if not text:
            raise ValueError("Record length cannot be empty.")
        label_key = text.upper().replace(" ", "")
        if label_key in RECORD_LENGTH_POINTS_BY_LABEL:
            return RECORD_LENGTH_POINTS_BY_LABEL[label_key]
        candidate = text
    else:
        candidate = record_length

    try:
        numeric = float(candidate)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Record length must be a positive integer point count or a supported label."
        ) from exc

    if not numeric.is_integer() or numeric <= 0:
        raise ValueError("Record length must be a positive integer point count.")
    return int(numeric)


def record_length_label(record_length: str | float | int) -> str:
    """Return a friendly label for common record lengths, otherwise the point count."""
    points = normalize_record_length(record_length)
    return RECORD_LENGTH_LABEL_BY_POINTS.get(points, str(points))


def build_record_length_command(record_length: str | float | int) -> str:
    return f"HORIZONTAL:RECORDLENGTH {normalize_record_length(record_length)}"


def build_record_length_query() -> str:
    return "HORIZONTAL:RECORDLENGTH?"


def normalize_trigger_level(level: str | float | int) -> str:
    text = str(level).strip()
    if not text:
        raise ValueError("Trigger level cannot be empty.")
    preset = text.upper()
    if preset in {"TTL", "ECL"}:
        return preset
    try:
        return f"{float(text):g}"
    except ValueError as exc:
        raise ValueError("Trigger level must be numeric volts, TTL, or ECL.") from exc


def build_edge_trigger_commands(
    *,
    source: str,
    slope: str,
    coupling: str,
    mode: str,
    level: str | float | int,
) -> list[str]:
    """Build common A-trigger commands for edge-trigger setup."""
    trigger_source = normalize_trigger_choice(source, TRIGGER_SOURCES, field="Trigger source")
    trigger_slope = normalize_trigger_choice(slope, TRIGGER_SLOPES, field="Trigger slope")
    trigger_coupling = normalize_trigger_choice(coupling, TRIGGER_COUPLINGS, field="Trigger coupling")
    trigger_mode = normalize_trigger_choice(mode, TRIGGER_MODES, field="Trigger mode")
    trigger_level = normalize_trigger_level(level)

    commands = [
        "TRIGGER:A:TYPE EDGE",
        f"TRIGGER:A:EDGE:SOURCE {trigger_source}",
        f"TRIGGER:A:EDGE:SLOPE {trigger_slope}",
        f"TRIGGER:A:EDGE:COUPLING {trigger_coupling}",
        f"TRIGGER:A:MODE {trigger_mode}",
    ]
    if trigger_source.startswith("CH"):
        commands.append(f"TRIGGER:A:LEVEL:{trigger_source} {trigger_level}")
    else:
        commands.append(f"TRIGGER:A:LEVEL {trigger_level}")
    return commands


class ControlMixin:
    """Mixin for scope display measurement, horizontal, and trigger controls."""

    def add_measurement(self, config: MeasurementConfig) -> None:
        scope = self.ensure_connected()
        for command in build_measurement_commands(config):
            scope.write(command)

    def disable_measurement(self, slot: int) -> None:
        self.ensure_connected().write(build_disable_measurement_command(slot))

    def disable_all_measurements(self) -> None:
        scope = self.ensure_connected()
        for slot in MEASUREMENT_SLOTS:
            scope.write(build_disable_measurement_command(slot))

    def read_measurement_value(self, slot: int) -> str:
        return self.ensure_connected().query(build_measurement_value_query(slot)).strip()

    def set_horizontal_position(self, position: str | float | int) -> None:
        self.ensure_connected().write(build_horizontal_position_command(position))

    def get_horizontal_position(self) -> float:
        response = self.ensure_connected().query(build_horizontal_position_query()).strip()
        return float(response.split()[-1])

    def nudge_horizontal_position(self, delta: str | float | int) -> float:
        current = self.get_horizontal_position()
        next_position = current + normalize_horizontal_position(delta)
        self.set_horizontal_position(next_position)
        return next_position

    def set_record_length(self, record_length: str | float | int) -> None:
        """Set horizontal acquisition record length in sample points."""
        self.ensure_connected().write(build_record_length_command(record_length))

    def get_record_length(self) -> int:
        """Read horizontal acquisition record length as integer sample points."""
        response = self.ensure_connected().query(build_record_length_query()).strip()
        return normalize_record_length(response.split()[-1])

    def configure_edge_trigger(
        self,
        *,
        source: str,
        slope: str,
        coupling: str,
        mode: str,
        level: str | float | int,
    ) -> None:
        scope = self.ensure_connected()
        for command in build_edge_trigger_commands(
            source=source,
            slope=slope,
            coupling=coupling,
            mode=mode,
            level=level,
        ):
            scope.write(command)

    def run_acquisition(self) -> None:
        self.ensure_connected().write("ACQUIRE:STATE RUN")

    def stop_acquisition(self) -> None:
        self.ensure_connected().write("ACQUIRE:STATE STOP")

    def single_acquisition(self) -> None:
        scope = self.ensure_connected()
        scope.write("ACQUIRE:STOPAFTER SEQUENCE")
        scope.write("ACQUIRE:STATE RUN")

    def continuous_acquisition(self) -> None:
        scope = self.ensure_connected()
        scope.write("ACQUIRE:STOPAFTER RUNSTOP")
        scope.write("ACQUIRE:STATE RUN")

    def force_trigger_event(self) -> None:
        self.ensure_connected().write(FORCE_TRIGGER_COMMAND)


__all__ = [
    "ControlMixin",
    "FORCE_TRIGGER_COMMAND",
    "MeasurementConfig",
    "MEASUREMENT_SLOTS",
    "MEASUREMENT_SOURCES",
    "MEASUREMENT_TYPES",
    "MEASUREMENT_TYPES_BY_GROUP",
    "RECORD_LENGTH_LABELS",
    "RECORD_LENGTH_LABEL_BY_POINTS",
    "RECORD_LENGTH_POINTS_BY_LABEL",
    "TRIGGER_COUPLINGS",
    "TRIGGER_MODES",
    "TRIGGER_SLOPES",
    "TRIGGER_SOURCES",
    "TRIGGER_TYPES",
    "build_disable_measurement_command",
    "build_edge_trigger_commands",
    "build_horizontal_position_command",
    "build_horizontal_position_query",
    "build_measurement_commands",
    "build_measurement_value_query",
    "build_record_length_command",
    "build_record_length_query",
    "normalize_record_length",
    "record_length_label",
]
