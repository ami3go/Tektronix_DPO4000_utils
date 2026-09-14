from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from dpo4000_utils.acquisition_state import TRIGGER_STATES
from dpo4000_utils.automation.periodic import MAX_PERIODIC_INTERVAL_S, MIN_PERIODIC_INTERVAL_S
from dpo4000_utils.automation.recovery import RecoveryPolicy
from dpo4000_utils.bus import BUS_SLOTS
from dpo4000_utils.control import (
    ACQUISITION_MODES,
    MEASUREMENT_SLOTS,
    RECORD_LENGTH_LABELS,
    AcquisitionConfig,
    ChannelConfig,
    MeasurementConfig,
    build_acquisition_setup_commands,
    build_channel_config_commands,
    build_edge_trigger_commands,
    build_measurement_commands,
)
from dpo4000_utils.logger.models import LoggerMode, LoggerOutputFormat
from dpo4000_utils.reference import REFERENCE_SLOTS


BASELINE = Path(__file__).with_name("regression") / "r0_functional_snapshot.json"


def _current_snapshot() -> dict[str, object]:
    return {
        "schema_version": 1,
        "indexed_resources": {
            "channels": [1, 2, 3, 4],
            "measurement_slots": list(MEASUREMENT_SLOTS),
            "bus_slots": list(BUS_SLOTS),
            "reference_slots": list(REFERENCE_SLOTS),
        },
        "normalized_enums": {
            "acquisition_modes": list(ACQUISITION_MODES),
            "trigger_states": list(TRIGGER_STATES),
            "record_length_labels": list(RECORD_LENGTH_LABELS),
            "logger_modes": [member.value for member in LoggerMode],
            "logger_output_formats": [member.value for member in LoggerOutputFormat],
        },
        "automation_contract": {
            "periodic_interval_min_s": MIN_PERIODIC_INTERVAL_S,
            "periodic_interval_max_s": MAX_PERIODIC_INTERVAL_S,
            "default_recovery": asdict(RecoveryPolicy()),
        },
        "command_contracts": {
            "channel_2": build_channel_config_commands(
                ChannelConfig(
                    channel=2,
                    display=True,
                    scale="0.5",
                    position="1",
                    offset="0.1",
                    coupling="ac",
                    bandwidth="20E6",
                    invert=False,
                    probe_gain="10",
                )
            ),
            "measurement_1_frequency": build_measurement_commands(
                MeasurementConfig(slot=1, measurement_type="frequency", source1="ch1")
            ),
            "edge_trigger_ch1": build_edge_trigger_commands(
                source="ch1",
                slope="rise",
                coupling="dc",
                mode="auto",
                level="1.25",
            ),
            "average_10k": build_acquisition_setup_commands(
                AcquisitionConfig(mode="average", average_count="16", record_length="10k")
            ),
        },
    }


def test_r0_functional_snapshot_is_unchanged() -> None:
    """Public normalized behavior changes require an explicit baseline review."""

    expected = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert _current_snapshot() == expected
