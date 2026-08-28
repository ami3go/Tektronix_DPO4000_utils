from __future__ import annotations

import pytest

from dpo4000_utils.reference import (
    ReferenceConfig,
    ReferenceMixin,
    build_reference_config_commands,
    build_reference_config_queries,
    build_save_waveform_to_reference_command,
    normalize_reference,
    normalize_reference_source,
)


def test_reference_config_queries_cover_display_geometry_and_metadata():
    assert build_reference_config_queries(2) == {
        "display": "SELECT:REF2?",
        "label": "REF2:LABEL?",
        "vertical_scale": "REF2:VERTICAL:SCALE?",
        "vertical_position": "REF2:VERTICAL:POSITION?",
        "horizontal_scale": "REF2:HORIZONTAL:SCALE?",
        "horizontal_delay": "REF2:HORIZONTAL:DELAY:TIME?",
        "date": "REF2:DATE?",
        "time": "REF2:TIME?",
    }


def test_reference_config_commands_match_dpo4000_programmer_manual():
    commands = build_reference_config_commands(
        ReferenceConfig(
            reference=3,
            display=True,
            label='Golden "pulse"',
            vertical_scale="0.1",
            vertical_position="-1.5",
            horizontal_scale="4E-6",
            horizontal_delay="2E-6",
        )
    )

    assert commands == [
        "REF3:LABEL \"Golden 'pulse'\"",
        "REF3:VERTICAL:SCALE 0.1",
        "REF3:VERTICAL:POSITION -1.5",
        "REF3:HORIZONTAL:SCALE 4E-6",
        "REF3:HORIZONTAL:DELAY:TIME 2E-6",
        "SELECT:REF3 ON",
    ]


def test_reference_label_can_be_cleared_and_is_limited_to_30_characters():
    clear = build_reference_config_commands(ReferenceConfig(reference=1, label=""))
    assert clear == ['REF1:LABEL ""']

    long_label = "x" * 40
    commands = build_reference_config_commands(ReferenceConfig(reference=1, label=long_label))
    assert commands == [f'REF1:LABEL "{"x" * 30}"']


def test_save_waveform_to_reference_command_accepts_live_math_and_other_refs():
    assert build_save_waveform_to_reference_command("ch1", 1) == "SAVE:WAVEFORM CH1,REF1"
    assert build_save_waveform_to_reference_command("math1", 2) == "SAVE:WAVEFORM MATH,REF2"
    assert build_save_waveform_to_reference_command("ref1", 2) == "SAVE:WAVEFORM REF1,REF2"


def test_reference_validation_rejects_invalid_slots_sources_and_self_copy():
    with pytest.raises(ValueError, match="between 1 and 4"):
        normalize_reference(5)
    with pytest.raises(ValueError, match="Unsupported reference waveform source"):
        normalize_reference_source("BUS1")
    with pytest.raises(ValueError, match="must be different"):
        build_save_waveform_to_reference_command("REF3", 3)


class FakeVisa:
    def __init__(self):
        self.writes: list[str] = []
        self.responses = {
            "SELECT:REF1?": ":SELECT:REF1 1",
            "REF1:LABEL?": ':REF1:LABEL "Golden"',
            "REF1:VERTICAL:SCALE?": ":REF1:VERTICAL:SCALE 1.0E-1",
            "REF1:VERTICAL:POSITION?": ":REF1:VERTICAL:POSITION -1.0",
            "REF1:HORIZONTAL:SCALE?": ":REF1:HORIZONTAL:SCALE 4.0E-6",
            "REF1:HORIZONTAL:DELAY:TIME?": ":REF1:HORIZONTAL:DELAY:TIME 2.0E-6",
            "REF1:DATE?": ':REF1:DATE "28-AUG-2026"',
            "REF1:TIME?": ':REF1:TIME "10:12:13"',
        }

    def query(self, command: str) -> str:
        return self.responses[command]

    def write(self, command: str) -> None:
        self.writes.append(command)


class ReferenceUnderTest(ReferenceMixin):
    def __init__(self):
        self.visa = FakeVisa()

    def ensure_connected(self):
        return self.visa


def test_reference_mixin_exposes_high_level_read_apply_and_store_api():
    driver = ReferenceUnderTest()

    config = driver.get_reference_configuration(1)
    assert config["display"] == "1"
    assert config["label"] == "Golden"
    assert config["vertical_scale"] == "1.0E-1"
    assert config["date"] == "28-AUG-2026"
    assert config["time"] == "10:12:13"

    driver.configure_reference(
        ReferenceConfig(reference=1, display=False, vertical_position="0")
    )
    driver.save_waveform_to_reference("CH2", 1)

    assert driver.visa.writes == [
        "REF1:VERTICAL:POSITION 0",
        "SELECT:REF1 OFF",
        "SAVE:WAVEFORM CH2,REF1",
    ]
