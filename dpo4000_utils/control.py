"""Scope control helpers shared by the Python API and DPO4000 Desk."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .channels import validate_channel


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
MEASUREMENT_SETUP_QUERIES = {
    "state": "MEASUREMENT:MEAS{slot}:STATE?",
    "type": "MEASUREMENT:MEAS{slot}:TYPE?",
    "source1": "MEASUREMENT:MEAS{slot}:SOURCE1?",
    "source2": "MEASUREMENT:MEAS{slot}:SOURCE2?",
    "value": "MEASUREMENT:MEAS{slot}:VALUE?",
}

TRIGGER_TYPES = ("EDGE", "PULSE", "RUNT", "TIMEOUT", "LOGIC", "VIDEO")
TRIGGER_MODES = ("AUTO", "NORMAL")
TRIGGER_SOURCES = ("CH1", "CH2", "CH3", "CH4", "AUX", "LINE")
TRIGGER_SLOPES = ("RISE", "FALL", "EITHER")
TRIGGER_COUPLINGS = ("DC", "AC", "HFREJ", "LFREJ", "NOISEREJ")
FORCE_TRIGGER_COMMAND = "TRIG FORC"

CHANNEL_CONFIG_FIELDS = (
    "display",
    "scale",
    "position",
    "offset",
    "coupling",
    "bandwidth",
    "invert",
    "probe_gain",
)
CHANNEL_CONFIG_QUERIES = {
    "display": "SELECT:CH{channel}?",
    "scale": "CH{channel}:SCALE?",
    "position": "CH{channel}:POSITION?",
    "offset": "CH{channel}:OFFSET?",
    "coupling": "CH{channel}:COUPLING?",
    "bandwidth": "CH{channel}:BANDWIDTH?",
    "invert": "CH{channel}:INVERT?",
    "probe_gain": "CH{channel}:PROBE:GAIN?",
}
MATH_CONFIG_FIELDS = ("display", "define", "scale", "position")
MATH_CONFIG_QUERIES = {
    "display": "SELECT:MATH?",
    "define": "MATH:DEFINE?",
    "scale": "MATH:VERTICAL:SCALE?",
    "position": "MATH:VERTICAL:POSITION?",
}

ACQUISITION_MODES = ("SAMPLE", "PEAKDETECT", "HIRES", "AVERAGE", "ENVELOPE")
AVERAGE_COUNTS = ("2", "4", "8", "16", "32", "64", "128", "256", "512")
ACQUISITION_SETUP_QUERIES = {
    "mode": "ACQUIRE:MODE?",
    "average_count": "ACQUIRE:NUMAVG?",
    "record_length": "HORIZONTAL:RECORDLENGTH?",
}
RECORD_LENGTH_LABELS = ("1k", "10k", "100k", "1M", "10M")
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

DISPLAY_PERSISTENCE_VALUES = ("AUTO", "MINIMUM", "INFINITE", "CLEAR", "0.5", "1", "2", "5", "10")
DISPLAY_SETUP_QUERIES = {
    "backlight": "DISPLAY:INTENSITY:BACKLIGHT?",
    "waveform": "DISPLAY:INTENSITY:WAVEFORM?",
    "graticule": "DISPLAY:INTENSITY:GRATICULE?",
    "persistence": "DISPLAY:PERSISTENCE?",
    "message_text": "MESSAGE:SHOW?",
    "message_state": "MESSAGE:STATE?",
}


@dataclass(frozen=True)
class MeasurementConfig:
    """One displayed measurement slot configuration."""

    slot: int
    measurement_type: str
    source1: str = "CH1"
    source2: str | None = None


@dataclass(frozen=True)
class ChannelConfig:
    """DPO4000 Desk channel configuration payload for one CH1..CH4 input."""

    channel: int
    display: bool | None = None
    scale: str | float | int | None = None
    position: str | float | int | None = None
    offset: str | float | int | None = None
    coupling: str | None = None
    bandwidth: str | float | int | None = None
    invert: bool | None = None
    probe_gain: str | float | int | None = None


@dataclass(frozen=True)
class MathConfig:
    """DPO4000 Desk MATH waveform configuration payload."""

    display: bool | None = None
    define: str | None = None
    scale: str | float | int | None = None
    position: str | float | int | None = None


@dataclass(frozen=True)
class AcquisitionConfig:
    """DPO4000 Desk acquisition setup payload."""

    mode: str | None = None
    average_count: str | int | None = None
    record_length: str | float | int | None = None


@dataclass(frozen=True)
class DisplayConfig:
    """DPO4000 Desk front-panel display setup payload."""

    backlight: str | float | int | None = None
    waveform: str | float | int | None = None
    graticule: str | float | int | None = None
    persistence: str | float | int | None = None
    message_text: str | None = None
    message_state: bool | None = None


@dataclass(frozen=True)
class MeasurementSetup:
    """Readback snapshot for one displayed MEAS slot."""

    slot: int
    state: str = ""
    measurement_type: str = ""
    source1: str = ""
    source2: str = ""
    value: str = ""


def _normalize_token(value: str, *, field: str) -> str:
    token = str(value or "").strip().upper()
    if not token:
        raise ValueError(f"{field} cannot be empty.")
    return token


def normalize_channel(channel: int | str) -> int:
    try:
        value = int(channel)
    except (TypeError, ValueError) as exc:
        raise ValueError("Channel must be an integer from 1 to 4.") from exc
    validate_channel(value)
    return value


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


def normalize_optional_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_scope_response_text(text: Any) -> str:
    """Extract the useful value from common Tektronix query responses."""
    value = str(text or "").strip()
    if '"' in value:
        return value.split('"', 1)[1].rsplit('"', 1)[0]
    return value.split()[-1] if value.split() else ""


def bool_from_scope_response(text: Any) -> bool:
    tokens = str(text or "").strip().upper().split()
    if not tokens:
        return False
    return tokens[-1] not in {"0", "OFF", "FALSE"}


def scpi_bool(value: bool) -> str:
    return "ON" if bool(value) else "OFF"


def quote_scpi_string(value: str) -> str:
    """Quote a single-line SCPI string and replace embedded double quotes."""
    clean = " ".join(str(value).replace('"', "'").splitlines()).strip()
    return f'"{clean}"'


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


def build_measurement_setup_queries(slot: int) -> dict[str, str]:
    valid_slot = validate_measurement_slot(slot)
    return {name: query.format(slot=valid_slot) for name, query in MEASUREMENT_SETUP_QUERIES.items()}


def build_disable_measurement_command(slot: int) -> str:
    return f"MEASUREMENT:MEAS{validate_measurement_slot(slot)}:STATE OFF"


def build_measurement_value_query(slot: int) -> str:
    return f"MEASUREMENT:MEAS{validate_measurement_slot(slot)}:VALUE?"


def build_channel_config_queries(channel: int | str) -> dict[str, str]:
    valid_channel = normalize_channel(channel)
    return {
        name: query.format(channel=valid_channel) for name, query in CHANNEL_CONFIG_QUERIES.items()
    }


def build_channel_config_commands(config: ChannelConfig) -> list[str]:
    channel = normalize_channel(config.channel)
    commands: list[str] = []
    if config.display is not None:
        commands.append(f"SELECT:CH{channel} {scpi_bool(config.display)}")
    for field, command in (
        (config.scale, f"CH{channel}:SCALE"),
        (config.position, f"CH{channel}:POSITION"),
        (config.offset, f"CH{channel}:OFFSET"),
        (config.coupling, f"CH{channel}:COUPLING"),
        (config.bandwidth, f"CH{channel}:BANDWIDTH"),
        (config.probe_gain, f"CH{channel}:PROBE:GAIN"),
    ):
        text = normalize_optional_text(field)
        if text:
            commands.append(f"{command} {text.upper() if command.endswith(':COUPLING') else text}")
    if config.invert is not None:
        commands.append(f"CH{channel}:INVERT {scpi_bool(config.invert)}")
    return commands


def build_math_config_queries() -> dict[str, str]:
    return dict(MATH_CONFIG_QUERIES)


def build_math_config_commands(config: MathConfig) -> list[str]:
    commands: list[str] = []
    expression = normalize_optional_text(config.define)
    if expression:
        commands.append(f"MATH:DEFINE {quote_scpi_string(expression)}")
    for field, command in (
        (config.scale, "MATH:VERTICAL:SCALE"),
        (config.position, "MATH:VERTICAL:POSITION"),
    ):
        text = normalize_optional_text(field)
        if text:
            commands.append(f"{command} {text}")
    if config.display is not None:
        commands.append(f"SELECT:MATH {scpi_bool(config.display)}")
    return commands


def normalize_horizontal_position(value: str | float | int) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Horizontal position must be a numeric value.") from exc


def build_horizontal_position_command(position: str | float | int) -> str:
    return f"HORIZONTAL:POSITION {normalize_horizontal_position(position):g}"


def build_horizontal_position_query() -> str:
    return "HORIZONTAL:POSITION?"


def normalize_acquisition_mode(mode: str) -> str:
    return normalize_trigger_choice(mode, ACQUISITION_MODES, field="Acquisition mode")


def normalize_average_count(count: str | int) -> int:
    try:
        value = int(str(count).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("Average count must be a positive integer.") from exc
    if value <= 0:
        raise ValueError("Average count must be a positive integer.")
    return value


def build_acquisition_mode_command(mode: str) -> str:
    return f"ACQUIRE:MODE {normalize_acquisition_mode(mode)}"


def build_acquisition_mode_query() -> str:
    return "ACQUIRE:MODE?"


def build_average_count_command(count: str | int) -> str:
    return f"ACQUIRE:NUMAVG {normalize_average_count(count)}"


def build_average_count_query() -> str:
    return "ACQUIRE:NUMAVG?"


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


def build_acquisition_setup_queries() -> dict[str, str]:
    return dict(ACQUISITION_SETUP_QUERIES)


def build_acquisition_setup_commands(config: AcquisitionConfig) -> list[str]:
    commands: list[str] = []
    normalized_mode = normalize_acquisition_mode(config.mode) if config.mode else ""
    if normalized_mode:
        commands.append(f"ACQUIRE:MODE {normalized_mode}")
    if config.average_count is not None and (not normalized_mode or normalized_mode == "AVERAGE"):
        commands.append(build_average_count_command(config.average_count))
    if config.record_length is not None:
        commands.append(build_record_length_command(config.record_length))
    return commands


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


def build_display_setup_queries() -> dict[str, str]:
    return dict(DISPLAY_SETUP_QUERIES)


def build_display_settings_commands(config: DisplayConfig) -> list[str]:
    commands: list[str] = []
    for field, command in (
        (config.backlight, "DISPLAY:INTENSITY:BACKLIGHT"),
        (config.waveform, "DISPLAY:INTENSITY:WAVEFORM"),
        (config.graticule, "DISPLAY:INTENSITY:GRATICULE"),
        (config.persistence, "DISPLAY:PERSISTENCE"),
    ):
        text = normalize_optional_text(field)
        if text:
            commands.append(f"{command} {text.upper() if command.endswith('PERSISTENCE') else text}")
    message_text = normalize_optional_text(config.message_text)
    if message_text:
        commands.append(f"MESSAGE:SHOW {quote_scpi_string(message_text)}")
    if config.message_state is not None:
        commands.append(f"MESSAGE:STATE {scpi_bool(config.message_state)}")
    return commands


def build_clear_display_message_commands() -> list[str]:
    return ["MESSAGE:CLEAR", "MESSAGE:STATE OFF"]


class ControlMixin:
    """Mixin for scope controls exposed by DPO4000 Desk."""

    @staticmethod
    def _query_optional(instrument: Any, command: str) -> str:
        try:
            response = instrument.query(command).strip()
        except Exception:
            return ""
        return normalize_scope_response_text(response)

    def query_identity(self) -> str:
        return self.ensure_connected().query("*IDN?").strip()

    def add_measurement(self, config: MeasurementConfig) -> None:
        scope = self.ensure_connected()
        for command in build_measurement_commands(config):
            scope.write(command)

    def get_measurement_setup(self, slot: int) -> MeasurementSetup:
        valid_slot = validate_measurement_slot(slot)
        scope = self.ensure_connected()
        values = {
            name: self._query_optional(scope, query)
            for name, query in build_measurement_setup_queries(valid_slot).items()
        }
        return MeasurementSetup(
            slot=valid_slot,
            state="ON" if bool_from_scope_response(values.get("state", "0")) else "OFF",
            measurement_type=values.get("type", ""),
            source1=values.get("source1", ""),
            source2=values.get("source2", ""),
            value=values.get("value", ""),
        )

    def get_all_measurement_setups(self) -> dict[int, MeasurementSetup]:
        return {slot: self.get_measurement_setup(slot) for slot in MEASUREMENT_SLOTS}

    def disable_measurement(self, slot: int) -> None:
        self.ensure_connected().write(build_disable_measurement_command(slot))

    def disable_all_measurements(self) -> None:
        scope = self.ensure_connected()
        for slot in MEASUREMENT_SLOTS:
            scope.write(build_disable_measurement_command(slot))

    def read_measurement_value(self, slot: int) -> str:
        return self.ensure_connected().query(build_measurement_value_query(slot)).strip()

    def configure_channel(self, config: ChannelConfig) -> None:
        scope = self.ensure_connected()
        for command in build_channel_config_commands(config):
            scope.write(command)

    def get_channel_configuration(self, channel: int | str) -> dict[str, str]:
        scope = self.ensure_connected()
        return {
            name: self._query_optional(scope, query)
            for name, query in build_channel_config_queries(channel).items()
        }

    def configure_math(self, config: MathConfig) -> None:
        scope = self.ensure_connected()
        for command in build_math_config_commands(config):
            scope.write(command)

    def get_math_configuration(self) -> dict[str, str]:
        scope = self.ensure_connected()
        return {name: self._query_optional(scope, query) for name, query in MATH_CONFIG_QUERIES.items()}

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

    def configure_acquisition(self, config: AcquisitionConfig) -> None:
        scope = self.ensure_connected()
        for command in build_acquisition_setup_commands(config):
            scope.write(command)

    def get_acquisition_setup(self) -> dict[str, str]:
        scope = self.ensure_connected()
        return {
            name: self._query_optional(scope, query)
            for name, query in build_acquisition_setup_queries().items()
        }

    def set_acquisition_mode(self, mode: str) -> None:
        self.ensure_connected().write(build_acquisition_mode_command(mode))

    def get_acquisition_mode(self) -> str:
        response = self.ensure_connected().query(build_acquisition_mode_query()).strip()
        return normalize_scope_response_text(response)

    def set_average_count(self, count: str | int) -> None:
        self.ensure_connected().write(build_average_count_command(count))

    def get_average_count(self) -> int:
        response = self.ensure_connected().query(build_average_count_query()).strip()
        return normalize_average_count(response.split()[-1])

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

    def apply_display_settings(self, config: DisplayConfig) -> None:
        scope = self.ensure_connected()
        for command in build_display_settings_commands(config):
            scope.write(command)

    def get_display_settings(self) -> dict[str, str]:
        scope = self.ensure_connected()
        return {
            name: self._query_optional(scope, query)
            for name, query in build_display_setup_queries().items()
        }

    def set_screen_message(self, text: str, *, state: bool = True) -> None:
        self.apply_display_settings(DisplayConfig(message_text=text, message_state=state))

    def clear_display_message(self) -> None:
        scope = self.ensure_connected()
        for command in build_clear_display_message_commands():
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
    "ACQUISITION_MODES",
    "ACQUISITION_SETUP_QUERIES",
    "AVERAGE_COUNTS",
    "AcquisitionConfig",
    "ChannelConfig",
    "ControlMixin",
    "DISPLAY_PERSISTENCE_VALUES",
    "DISPLAY_SETUP_QUERIES",
    "DisplayConfig",
    "FORCE_TRIGGER_COMMAND",
    "MATH_CONFIG_FIELDS",
    "MATH_CONFIG_QUERIES",
    "MEASUREMENT_SETUP_QUERIES",
    "MATH_CONFIG_FIELDS",
    "MathConfig",
    "MeasurementConfig",
    "MeasurementSetup",
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
    "bool_from_scope_response",
    "build_acquisition_mode_command",
    "build_acquisition_mode_query",
    "build_acquisition_setup_commands",
    "build_acquisition_setup_queries",
    "build_average_count_command",
    "build_average_count_query",
    "build_channel_config_commands",
    "build_channel_config_queries",
    "build_clear_display_message_commands",
    "build_disable_measurement_command",
    "build_display_settings_commands",
    "build_display_setup_queries",
    "build_edge_trigger_commands",
    "build_horizontal_position_command",
    "build_horizontal_position_query",
    "build_math_config_commands",
    "build_math_config_queries",
    "build_measurement_commands",
    "build_measurement_setup_queries",
    "build_measurement_value_query",
    "build_record_length_command",
    "build_record_length_query",
    "normalize_acquisition_mode",
    "normalize_average_count",
    "normalize_channel",
    "normalize_record_length",
    "normalize_scope_response_text",
    "quote_scpi_string",
    "record_length_label",
    "scpi_bool",
]
