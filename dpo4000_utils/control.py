"""Scope control helpers shared by the Python API and DPO4000 Desk."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .channels import validate_channel
from .io_policy import optional_query, required_query
from .scpi_values import (
    ensure_single_scpi_value,
    format_scpi_number,
    normalize_scpi_enum,
    normalize_scpi_token,
)


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

TRIGGER_TYPES = ("EDGE", "LOGIC", "PULSE", "VIDEO", "BUS")
TRIGGER_MODES = ("AUTO", "NORMAL")
TRIGGER_SOURCES = ("CH1", "CH2", "CH3", "CH4", "AUX", "LINE")
TRIGGER_SLOPES = ("RISE", "FALL", "EITHER")
TRIGGER_COUPLINGS = ("DC", "AC", "HFREJ", "LFREJ", "NOISEREJ")
FORCE_TRIGGER_COMMAND = "TRIG FORC"

# TRIGGER:A:TYPE PULSE selects one of these via TRIGGER:A:PULSE:CLASS. Live-verified
# against a DPO4054 (see docs/a14-advanced-trigger-backlog.md); TRANSITION's own field
# layout is not yet mapped, so it is accepted as a class but has no field support below.
TRIGGER_PULSE_CLASSES = ("WIDTH", "RUNT", "TIMEOUT", "TRANSITION")
TRIGGER_PULSE_WIDTH_POLARITIES = ("POSITIVE", "NEGATIVE")
TRIGGER_PULSE_WIDTH_WHEN = ("LESSTHAN", "MORETHAN", "EQUAL", "UNEQUAL", "WITHIN", "OUTSIDE")
TRIGGER_PULSE_RUNT_POLARITIES = ("POSITIVE", "NEGATIVE", "EITHER")
TRIGGER_PULSE_RUNT_WHEN = ("OCCURS", "LESSTHAN", "MORETHAN", "EQUAL", "UNEQUAL")
TRIGGER_PULSE_TIMEOUT_POLARITIES = ("STAYSHIGH", "STAYSLOW", "EITHER")

# TRIGGER:A:TYPE LOGIC selects one of these via TRIGGER:A:LOGIC:CLASS. Live-verified
# against a DPO4054 (see docs/a14-advanced-trigger-backlog.md). SETHOLD's DATA:SOURCE
# leaf could not be found by probing and remains unmapped/unsettable here.
TRIGGER_LOGIC_CLASSES = ("LOGIC", "SETHOLD")
TRIGGER_LOGIC_FUNCTIONS = ("AND", "OR", "NAND", "NOR")
TRIGGER_LOGIC_INPUT_STATES = ("HIGH", "LOW", "X")
TRIGGER_LOGIC_CLOCK_SOURCES = ("CH1", "CH2", "CH3", "CH4", "NONE")
TRIGGER_LOGIC_CLOCK_EDGES = ("RISE", "FALL")
TRIGGER_LOGIC_PATTERN_WHEN = ("TRUE", "FALSE", "LESSTHAN", "MORETHAN")

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


@dataclass(frozen=True)
class TriggerConfig:
    """DPO4000 Desk A-trigger configuration payload.

    Only EDGE, PULSE (classes WIDTH/RUNT/TIMEOUT), and LOGIC (classes LOGIC/SETHOLD)
    are supported by ``configure_trigger()`` today; see
    docs/a14-advanced-trigger-backlog.md for the remaining trigger types, which need
    their SCPI subtree verified against real hardware before being added here.
    """

    trigger_type: str
    # Shared with EDGE (build_edge_trigger_commands requires all five when trigger_type
    # is EDGE) and, for mode/source, with PULSE.
    mode: str | None = None
    source: str | None = None
    slope: str | None = None
    coupling: str | None = None
    level: str | float | int | None = None
    # PULSE only.
    pulse_class: str | None = None
    pulse_polarity: str | None = None
    pulse_when: str | None = None
    pulse_low_limit: str | float | int | None = None
    pulse_high_limit: str | float | int | None = None
    pulse_threshold_high: str | float | int | None = None
    pulse_threshold_low: str | float | int | None = None
    pulse_timeout_time: str | float | int | None = None
    # LOGIC only. logic_clock_source/logic_clock_edge are shared between the LOGIC and
    # SETHOLD classes (each writes a different SCPI leaf; only one class is active per
    # config). SETHOLD's data source is not settable - its SCPI leaf could not be found.
    logic_class: str | None = None
    logic_function: str | None = None
    logic_input_ch1: str | None = None
    logic_input_ch2: str | None = None
    logic_input_ch3: str | None = None
    logic_input_ch4: str | None = None
    logic_clock_source: str | None = None
    logic_clock_edge: str | None = None
    logic_when: str | None = None
    logic_clock_threshold: str | float | int | None = None
    logic_data_threshold: str | float | int | None = None
    logic_setup_time: str | float | int | None = None
    logic_hold_time: str | float | int | None = None


def _normalize_token(value: str, *, field: str) -> str:
    return normalize_scpi_token(value, field=field, uppercase=True)


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
    return normalize_scpi_enum(measurement_type, MEASUREMENT_TYPES, field="Measurement type")


def normalize_trigger_choice(value: str, allowed: tuple[str, ...], *, field: str) -> str:
    return normalize_scpi_enum(value, allowed, field=field)


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
    """Quote one SCPI string while removing physical line breaks and unsafe quotes."""
    clean = " ".join(str(value).replace('"', "'").splitlines()).strip()
    return f'"{clean}"'


def build_measurement_commands(config: MeasurementConfig) -> list[str]:
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


def _normalize_bandwidth(value: Any) -> str:
    token = ensure_single_scpi_value(value, field="Channel bandwidth")
    if token.upper() == "FULL":
        return "FULL"
    return format_scpi_number(token, field="Channel bandwidth", positive=True)


def build_channel_config_commands(config: ChannelConfig) -> list[str]:
    channel = normalize_channel(config.channel)
    commands: list[str] = []
    if config.display is not None:
        commands.append(f"SELECT:CH{channel} {scpi_bool(config.display)}")
    if config.scale is not None:
        commands.append(
            f"CH{channel}:SCALE {format_scpi_number(config.scale, field='Channel scale', positive=True)}"
        )
    if config.position is not None:
        commands.append(
            f"CH{channel}:POSITION {format_scpi_number(config.position, field='Channel position')}"
        )
    if config.offset is not None:
        commands.append(
            f"CH{channel}:OFFSET {format_scpi_number(config.offset, field='Channel offset')}"
        )
    if config.coupling is not None:
        coupling = normalize_scpi_enum(config.coupling, ("AC", "DC", "GND"), field="Channel coupling")
        commands.append(f"CH{channel}:COUPLING {coupling}")
    if config.bandwidth is not None:
        commands.append(f"CH{channel}:BANDWIDTH {_normalize_bandwidth(config.bandwidth)}")
    if config.probe_gain is not None:
        commands.append(
            f"CH{channel}:PROBE:GAIN {format_scpi_number(config.probe_gain, field='Probe gain', positive=True)}"
        )
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
    if config.scale is not None:
        commands.append(
            f"MATH:VERTICAL:SCALE {format_scpi_number(config.scale, field='MATH scale', positive=True)}"
        )
    if config.position is not None:
        commands.append(
            f"MATH:VERTICAL:POSITION {format_scpi_number(config.position, field='MATH position')}"
        )
    if config.display is not None:
        commands.append(f"SELECT:MATH {scpi_bool(config.display)}")
    return commands


def normalize_horizontal_position(value: str | float | int) -> float:
    return float(format_scpi_number(value, field="Horizontal position"))


def build_horizontal_position_command(position: str | float | int) -> str:
    return f"HORIZONTAL:POSITION {format_scpi_number(position, field='Horizontal position')}"


def build_horizontal_position_query() -> str:
    return "HORIZONTAL:POSITION?"


def normalize_acquisition_mode(mode: str) -> str:
    return normalize_trigger_choice(mode, ACQUISITION_MODES, field="Acquisition mode")


def normalize_average_count(count: str | int) -> int:
    return int(format_scpi_number(count, field="Average count", positive=True, integer=True))


def build_acquisition_mode_command(mode: str) -> str:
    return f"ACQUIRE:MODE {normalize_acquisition_mode(mode)}"


def build_acquisition_mode_query() -> str:
    return "ACQUIRE:MODE?"


def build_average_count_command(count: str | int) -> str:
    return f"ACQUIRE:NUMAVG {normalize_average_count(count)}"


def build_average_count_query() -> str:
    return "ACQUIRE:NUMAVG?"


def normalize_record_length(record_length: str | float | int) -> int:
    if isinstance(record_length, bool):
        raise ValueError("Record length must be a positive integer point count or label.")
    if isinstance(record_length, str):
        text = ensure_single_scpi_value(record_length, field="Record length")
        label_key = text.upper().replace(" ", "")
        if label_key in RECORD_LENGTH_POINTS_BY_LABEL:
            return RECORD_LENGTH_POINTS_BY_LABEL[label_key]
        candidate: Any = text
    else:
        candidate = record_length
    return int(
        format_scpi_number(
            candidate,
            field="Record length",
            positive=True,
            integer=True,
        )
    )


def record_length_label(record_length: str | float | int) -> str:
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
    text = ensure_single_scpi_value(level, field="Trigger level")
    preset = text.upper()
    if preset in {"TTL", "ECL"}:
        return preset
    return format_scpi_number(text, field="Trigger level")


def build_edge_trigger_commands(
    *,
    source: str,
    slope: str,
    coupling: str,
    mode: str,
    level: str | float | int,
) -> list[str]:
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


_TRIGGER_PULSE_CLASS_QUERIES: dict[str, dict[str, str]] = {
    "WIDTH": {
        "pulse_polarity": "TRIGGER:A:PULSE:WIDTH:POLARITY?",
        "pulse_when": "TRIGGER:A:PULSE:WIDTH:WHEN?",
        "pulse_low_limit": "TRIGGER:A:PULSE:WIDTH:LOWLIMIT?",
        "pulse_high_limit": "TRIGGER:A:PULSE:WIDTH:HIGHLIMIT?",
    },
    "RUNT": {
        "pulse_polarity": "TRIGGER:A:PULSE:RUNT:POLARITY?",
        "pulse_when": "TRIGGER:A:PULSE:RUNT:WHEN?",
        "pulse_threshold_high": "TRIGGER:A:PULSE:RUNT:THRESHOLD:HIGH?",
        "pulse_threshold_low": "TRIGGER:A:PULSE:RUNT:THRESHOLD:LOW?",
        "pulse_low_limit": "TRIGGER:A:PULSE:RUNT:LOWLIMIT?",
        "pulse_high_limit": "TRIGGER:A:PULSE:RUNT:HIGHLIMIT?",
    },
    "TIMEOUT": {
        "pulse_polarity": "TRIGGER:A:PULSE:TIMEOUT:POLARITY?",
        "pulse_timeout_time": "TRIGGER:A:PULSE:TIMEOUT:TIME?",
    },
}


def _build_pulse_trigger_commands(config: TriggerConfig) -> list[str]:
    commands = ["TRIGGER:A:TYPE PULSE"]
    pulse_class = (
        normalize_scpi_enum(config.pulse_class, TRIGGER_PULSE_CLASSES, field="Pulse trigger class")
        if config.pulse_class is not None
        else None
    )
    if pulse_class is not None:
        commands.append(f"TRIGGER:A:PULSE:CLASS {pulse_class}")
    if config.source is not None:
        source = normalize_trigger_choice(config.source, TRIGGER_SOURCES, field="Pulse trigger source")
        commands.append(f"TRIGGER:A:PULSE:SOURCE {source}")

    if pulse_class == "WIDTH":
        if config.pulse_polarity is not None:
            polarity = normalize_scpi_enum(
                config.pulse_polarity, TRIGGER_PULSE_WIDTH_POLARITIES, field="Pulse width polarity"
            )
            commands.append(f"TRIGGER:A:PULSE:WIDTH:POLARITY {polarity}")
        if config.pulse_when is not None:
            when = normalize_scpi_enum(
                config.pulse_when, TRIGGER_PULSE_WIDTH_WHEN, field="Pulse width comparator"
            )
            commands.append(f"TRIGGER:A:PULSE:WIDTH:WHEN {when}")
        if config.pulse_low_limit is not None:
            limit = format_scpi_number(config.pulse_low_limit, field="Pulse width low limit", nonnegative=True)
            commands.append(f"TRIGGER:A:PULSE:WIDTH:LOWLIMIT {limit}")
        if config.pulse_high_limit is not None:
            limit = format_scpi_number(config.pulse_high_limit, field="Pulse width high limit", nonnegative=True)
            commands.append(f"TRIGGER:A:PULSE:WIDTH:HIGHLIMIT {limit}")
    elif pulse_class == "RUNT":
        if config.pulse_polarity is not None:
            polarity = normalize_scpi_enum(
                config.pulse_polarity, TRIGGER_PULSE_RUNT_POLARITIES, field="Pulse runt polarity"
            )
            commands.append(f"TRIGGER:A:PULSE:RUNT:POLARITY {polarity}")
        if config.pulse_when is not None:
            when = normalize_scpi_enum(
                config.pulse_when, TRIGGER_PULSE_RUNT_WHEN, field="Pulse runt comparator"
            )
            commands.append(f"TRIGGER:A:PULSE:RUNT:WHEN {when}")
        if config.pulse_threshold_high is not None:
            threshold = format_scpi_number(config.pulse_threshold_high, field="Pulse runt high threshold")
            commands.append(f"TRIGGER:A:PULSE:RUNT:THRESHOLD:HIGH {threshold}")
        if config.pulse_threshold_low is not None:
            threshold = format_scpi_number(config.pulse_threshold_low, field="Pulse runt low threshold")
            commands.append(f"TRIGGER:A:PULSE:RUNT:THRESHOLD:LOW {threshold}")
        if config.pulse_low_limit is not None:
            limit = format_scpi_number(config.pulse_low_limit, field="Pulse runt low limit", nonnegative=True)
            commands.append(f"TRIGGER:A:PULSE:RUNT:LOWLIMIT {limit}")
        if config.pulse_high_limit is not None:
            limit = format_scpi_number(config.pulse_high_limit, field="Pulse runt high limit", nonnegative=True)
            commands.append(f"TRIGGER:A:PULSE:RUNT:HIGHLIMIT {limit}")
    elif pulse_class == "TIMEOUT":
        if config.pulse_polarity is not None:
            polarity = normalize_scpi_enum(
                config.pulse_polarity, TRIGGER_PULSE_TIMEOUT_POLARITIES, field="Pulse timeout polarity"
            )
            commands.append(f"TRIGGER:A:PULSE:TIMEOUT:POLARITY {polarity}")
        if config.pulse_timeout_time is not None:
            timeout_time = format_scpi_number(
                config.pulse_timeout_time, field="Pulse timeout time", nonnegative=True
            )
            commands.append(f"TRIGGER:A:PULSE:TIMEOUT:TIME {timeout_time}")

    if config.mode is not None:
        mode = normalize_trigger_choice(config.mode, TRIGGER_MODES, field="Trigger mode")
        commands.append(f"TRIGGER:A:MODE {mode}")
    return commands


_TRIGGER_LOGIC_CLASS_QUERIES: dict[str, dict[str, str]] = {
    "LOGIC": {
        "logic_function": "TRIGGER:A:LOGIC:FUNCTION?",
        "logic_input_ch1": "TRIGGER:A:LOGIC:INPUT:CH1?",
        "logic_input_ch2": "TRIGGER:A:LOGIC:INPUT:CH2?",
        "logic_input_ch3": "TRIGGER:A:LOGIC:INPUT:CH3?",
        "logic_input_ch4": "TRIGGER:A:LOGIC:INPUT:CH4?",
        "logic_clock_source": "TRIGGER:A:LOGIC:INPUT:CLOCK:SOURCE?",
        "logic_clock_edge": "TRIGGER:A:LOGIC:INPUT:CLOCK:EDGE?",
        "logic_when": "TRIGGER:A:LOGIC:PATTERN:WHEN?",
    },
    "SETHOLD": {
        "logic_clock_source": "TRIGGER:A:LOGIC:SETHOLD:CLOCK:SOURCE?",
        "logic_clock_edge": "TRIGGER:A:LOGIC:SETHOLD:CLOCK:EDGE?",
        "logic_clock_threshold": "TRIGGER:A:LOGIC:SETHOLD:CLOCK:THRESHOLD?",
        "logic_data_threshold": "TRIGGER:A:LOGIC:SETHOLD:DATA:THRESHOLD?",
        "logic_setup_time": "TRIGGER:A:LOGIC:SETHOLD:SETTIME?",
        "logic_hold_time": "TRIGGER:A:LOGIC:SETHOLD:HOLDTIME?",
    },
}


def _build_logic_trigger_commands(config: TriggerConfig) -> list[str]:
    commands = ["TRIGGER:A:TYPE LOGIC"]
    logic_class = (
        normalize_scpi_enum(config.logic_class, TRIGGER_LOGIC_CLASSES, field="Logic trigger class")
        if config.logic_class is not None
        else None
    )
    if logic_class is not None:
        commands.append(f"TRIGGER:A:LOGIC:CLASS {logic_class}")

    if logic_class == "LOGIC":
        if config.logic_function is not None:
            function = normalize_scpi_enum(
                config.logic_function, TRIGGER_LOGIC_FUNCTIONS, field="Logic trigger function"
            )
            commands.append(f"TRIGGER:A:LOGIC:FUNCTION {function}")
        for channel, value in (
            (1, config.logic_input_ch1),
            (2, config.logic_input_ch2),
            (3, config.logic_input_ch3),
            (4, config.logic_input_ch4),
        ):
            if value is not None:
                state = normalize_scpi_enum(
                    value, TRIGGER_LOGIC_INPUT_STATES, field=f"Logic input CH{channel} state"
                )
                commands.append(f"TRIGGER:A:LOGIC:INPUT:CH{channel} {state}")
        if config.logic_clock_source is not None:
            clock_source = normalize_scpi_enum(
                config.logic_clock_source, TRIGGER_LOGIC_CLOCK_SOURCES, field="Logic clock source"
            )
            commands.append(f"TRIGGER:A:LOGIC:INPUT:CLOCK:SOURCE {clock_source}")
        if config.logic_clock_edge is not None:
            clock_edge = normalize_scpi_enum(
                config.logic_clock_edge, TRIGGER_LOGIC_CLOCK_EDGES, field="Logic clock edge"
            )
            commands.append(f"TRIGGER:A:LOGIC:INPUT:CLOCK:EDGE {clock_edge}")
        if config.logic_when is not None:
            when = normalize_scpi_enum(
                config.logic_when, TRIGGER_LOGIC_PATTERN_WHEN, field="Logic pattern comparator"
            )
            commands.append(f"TRIGGER:A:LOGIC:PATTERN:WHEN {when}")
    elif logic_class == "SETHOLD":
        if config.logic_clock_source is not None:
            clock_source = normalize_scpi_enum(
                config.logic_clock_source, TRIGGER_LOGIC_CLOCK_SOURCES, field="Logic clock source"
            )
            commands.append(f"TRIGGER:A:LOGIC:SETHOLD:CLOCK:SOURCE {clock_source}")
        if config.logic_clock_edge is not None:
            clock_edge = normalize_scpi_enum(
                config.logic_clock_edge, TRIGGER_LOGIC_CLOCK_EDGES, field="Logic clock edge"
            )
            commands.append(f"TRIGGER:A:LOGIC:SETHOLD:CLOCK:EDGE {clock_edge}")
        if config.logic_clock_threshold is not None:
            threshold = format_scpi_number(config.logic_clock_threshold, field="Logic clock threshold")
            commands.append(f"TRIGGER:A:LOGIC:SETHOLD:CLOCK:THRESHOLD {threshold}")
        if config.logic_data_threshold is not None:
            threshold = format_scpi_number(config.logic_data_threshold, field="Logic data threshold")
            commands.append(f"TRIGGER:A:LOGIC:SETHOLD:DATA:THRESHOLD {threshold}")
        if config.logic_setup_time is not None:
            setup_time = format_scpi_number(
                config.logic_setup_time, field="Logic setup time", nonnegative=True
            )
            commands.append(f"TRIGGER:A:LOGIC:SETHOLD:SETTIME {setup_time}")
        if config.logic_hold_time is not None:
            hold_time = format_scpi_number(
                config.logic_hold_time, field="Logic hold time", nonnegative=True
            )
            commands.append(f"TRIGGER:A:LOGIC:SETHOLD:HOLDTIME {hold_time}")

    if config.mode is not None:
        mode = normalize_trigger_choice(config.mode, TRIGGER_MODES, field="Trigger mode")
        commands.append(f"TRIGGER:A:MODE {mode}")
    return commands


def build_trigger_config_commands(config: TriggerConfig) -> list[str]:
    """Build the A-trigger SCPI command sequence for one :class:`TriggerConfig`.

    Only EDGE, PULSE (WIDTH/RUNT/TIMEOUT classes), and LOGIC (LOGIC/SETHOLD classes)
    are supported; see docs/a14-advanced-trigger-backlog.md for the remaining trigger
    types.
    """
    trigger_type = normalize_scpi_enum(config.trigger_type, TRIGGER_TYPES, field="Trigger type")
    if trigger_type == "EDGE":
        missing = [
            name
            for name, value in (
                ("source", config.source),
                ("slope", config.slope),
                ("coupling", config.coupling),
                ("mode", config.mode),
                ("level", config.level),
            )
            if value is None
        ]
        if missing:
            raise ValueError(f"EDGE trigger requires {', '.join(missing)} to be set.")
        return build_edge_trigger_commands(
            source=config.source,
            slope=config.slope,
            coupling=config.coupling,
            mode=config.mode,
            level=config.level,
        )
    if trigger_type == "PULSE":
        return _build_pulse_trigger_commands(config)
    if trigger_type == "LOGIC":
        return _build_logic_trigger_commands(config)
    raise ValueError(
        f"Trigger type {trigger_type!r} is not yet supported by configure_trigger(); "
        "see docs/a14-advanced-trigger-backlog.md for its verification status."
    )


def build_trigger_config_queries(
    trigger_type: str, pulse_class: str | None = None, logic_class: str | None = None
) -> dict[str, str]:
    """Return the read-back query set for one trigger type (and PULSE/LOGIC class)."""
    normalized_type = normalize_scpi_enum(trigger_type, TRIGGER_TYPES, field="Trigger type")
    if normalized_type == "PULSE":
        queries = {"source": "TRIGGER:A:PULSE:SOURCE?"}
        if pulse_class is not None:
            normalized_class = normalize_scpi_enum(
                pulse_class, TRIGGER_PULSE_CLASSES, field="Pulse trigger class"
            )
            queries.update(_TRIGGER_PULSE_CLASS_QUERIES.get(normalized_class, {}))
        return queries
    if normalized_type == "LOGIC":
        if logic_class is None:
            return {}
        normalized_class = normalize_scpi_enum(
            logic_class, TRIGGER_LOGIC_CLASSES, field="Logic trigger class"
        )
        return dict(_TRIGGER_LOGIC_CLASS_QUERIES.get(normalized_class, {}))
    raise ValueError(
        f"Trigger type {normalized_type!r} is not yet supported by get_trigger_configuration(); "
        "see docs/a14-advanced-trigger-backlog.md for its verification status."
    )


def build_display_setup_queries() -> dict[str, str]:
    return dict(DISPLAY_SETUP_QUERIES)


def _normalize_display_intensity(value: Any, *, field: str) -> str:
    text = ensure_single_scpi_value(value, field=field)
    if text.upper() in {"LOW", "MEDIUM", "HIGH"}:
        return text.upper()
    return format_scpi_number(text, field=field, nonnegative=True)


def _normalize_persistence(value: Any) -> str:
    text = ensure_single_scpi_value(value, field="Display persistence")
    if text.upper() in {"AUTO", "MINIMUM", "INFINITE", "CLEAR"}:
        return text.upper()
    return format_scpi_number(text, field="Display persistence", nonnegative=True)


def build_display_settings_commands(config: DisplayConfig) -> list[str]:
    commands: list[str] = []
    if config.backlight is not None:
        commands.append(
            f"DISPLAY:INTENSITY:BACKLIGHT {_normalize_display_intensity(config.backlight, field='Backlight intensity')}"
        )
    if config.waveform is not None:
        commands.append(
            f"DISPLAY:INTENSITY:WAVEFORM {_normalize_display_intensity(config.waveform, field='Waveform intensity')}"
        )
    if config.graticule is not None:
        commands.append(
            f"DISPLAY:INTENSITY:GRATICULE {_normalize_display_intensity(config.graticule, field='Graticule intensity')}"
        )
    if config.persistence is not None:
        commands.append(f"DISPLAY:PERSISTENCE {_normalize_persistence(config.persistence)}")
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
        return optional_query(instrument, command, normalizer=normalize_scope_response_text)

    def query_identity(self) -> str:
        return required_query(
            self.ensure_connected(),
            "*IDN?",
            operation="Reading oscilloscope identity",
        )

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
        self.ensure_connected().write(build_record_length_command(record_length))

    def get_record_length(self) -> int:
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

    def configure_trigger(self, config: TriggerConfig) -> None:
        """Apply an A-trigger configuration (EDGE or PULSE today).

        Additive to ``configure_edge_trigger()``, which is unchanged and remains the
        supported path for edge-only callers. See docs/a14-advanced-trigger-backlog.md.
        """
        scope = self.ensure_connected()
        for command in build_trigger_config_commands(config):
            scope.write(command)

    def get_trigger_configuration(self) -> dict[str, Any]:
        """Read back the A-trigger configuration for its current type.

        Only EDGE, PULSE (WIDTH/RUNT/TIMEOUT classes), and LOGIC (LOGIC/SETHOLD
        classes) are supported today; other types return just
        ``{"trigger_type": <raw readback>}``.
        """
        scope = self.ensure_connected()
        raw_type = self._query_optional(scope, "TRIGGER:A:TYPE?").upper()
        if raw_type == "EDG":
            result: dict[str, Any] = {"trigger_type": "EDGE"}
            result.update(self.get_edge_trigger_configuration())
            return result
        if raw_type == "PULS":
            raw_class = self._query_optional(scope, "TRIGGER:A:PULSE:CLASS?").upper()
            class_by_readback = {"WID": "WIDTH", "RUN": "RUNT", "TIMEO": "TIMEOUT", "TRAN": "TRANSITION"}
            pulse_class = class_by_readback.get(raw_class)
            result = {"trigger_type": "PULSE", "pulse_class": pulse_class or raw_class}
            queries = {"source": "TRIGGER:A:PULSE:SOURCE?"}
            if pulse_class is not None:
                queries.update(_TRIGGER_PULSE_CLASS_QUERIES.get(pulse_class, {}))
            result.update({name: self._query_optional(scope, query) for name, query in queries.items()})
            return result
        if raw_type == "LOGI":
            raw_class = self._query_optional(scope, "TRIGGER:A:LOGIC:CLASS?").upper()
            class_by_readback = {"LOGI": "LOGIC", "SETH": "SETHOLD"}
            logic_class = class_by_readback.get(raw_class)
            result = {"trigger_type": "LOGIC", "logic_class": logic_class or raw_class}
            queries = _TRIGGER_LOGIC_CLASS_QUERIES.get(logic_class, {}) if logic_class else {}
            result.update({name: self._query_optional(scope, query) for name, query in queries.items()})
            return result
        return {"trigger_type": raw_type}

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
    "TRIGGER_LOGIC_CLASSES",
    "TRIGGER_LOGIC_CLOCK_EDGES",
    "TRIGGER_LOGIC_CLOCK_SOURCES",
    "TRIGGER_LOGIC_FUNCTIONS",
    "TRIGGER_LOGIC_INPUT_STATES",
    "TRIGGER_LOGIC_PATTERN_WHEN",
    "TRIGGER_PULSE_CLASSES",
    "TRIGGER_PULSE_RUNT_POLARITIES",
    "TRIGGER_PULSE_RUNT_WHEN",
    "TRIGGER_PULSE_TIMEOUT_POLARITIES",
    "TRIGGER_PULSE_WIDTH_POLARITIES",
    "TRIGGER_PULSE_WIDTH_WHEN",
    "TRIGGER_SLOPES",
    "TRIGGER_SOURCES",
    "TRIGGER_TYPES",
    "TriggerConfig",
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
    "build_trigger_config_commands",
    "build_trigger_config_queries",
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
