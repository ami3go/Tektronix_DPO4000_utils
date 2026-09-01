"""Opt-in hardware API tests for a real Tektronix DPO4000-family scope.

These tests are skipped unless explicitly enabled with environment variables.
They are designed for a bench PC or self-hosted CI runner that has:

- a connected DPO4000-family oscilloscope,
- a working VISA runtime such as NI-VISA/TekVISA/Keysight VISA,
- PyVISA installed through this package.
"""

from __future__ import annotations

import math
import os
from collections.abc import Iterator

import pytest

from dpo4000_utils import DPO4054
from dpo4000_utils.connection import visaResourceAddr
from dpo4000_utils.waveform import parse_channel_enabled

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def _hardware_resource() -> str:
    return os.getenv("DPO4000_RESOURCE", visaResourceAddr).strip()


@pytest.fixture(scope="session")
def hardware_enabled() -> str:
    """Return configured resource name or skip when hardware tests are disabled."""
    if not _env_enabled("DPO4000_HARDWARE"):
        pytest.skip("Set DPO4000_HARDWARE=1 to run real oscilloscope tests.")

    resource = _hardware_resource()
    if not resource:
        pytest.skip("Set DPO4000_RESOURCE to the VISA resource of the oscilloscope.")
    return resource


@pytest.fixture(scope="session")
def scope(hardware_enabled: str) -> Iterator[DPO4054]:
    """Open one real scope session for the hardware test module."""
    instrument = DPO4054(hardware_enabled, auto_connect=False)
    instrument.connect()

    timeout_ms = int(os.getenv("DPO4000_TIMEOUT_MS", "20000"))
    if instrument.scope is not None:
        instrument.scope.timeout = timeout_ms

    try:
        yield instrument
    finally:
        instrument.disconnect()


@pytest.mark.hardware
def test_hardware_connects_and_identifies_scope(scope: DPO4054) -> None:
    """Verify that the configured VISA resource responds to *IDN?."""
    assert scope.scope is not None
    idn = scope.scope.query("*IDN?").strip()

    expected = os.getenv("DPO4000_EXPECT_IDN", "TEKTRONIX").strip()
    assert idn
    assert expected.upper() in idn.upper()


@pytest.mark.hardware
def test_hardware_reads_all_channel_labels(scope: DPO4054) -> None:
    """Verify the public channel label read API on CH1..CH4."""
    labels = scope.get_channel_labels()
    assert set(labels) == {1, 2, 3, 4}
    assert all(isinstance(label, str) for label in labels.values())


@pytest.mark.hardware
def test_hardware_reads_trigger_level(scope: DPO4054) -> None:
    """Verify the public trigger-level read API without changing setup."""
    value = scope.get_trigger_level(channel=1)
    assert isinstance(value, float | str)
    assert str(value).strip()


@pytest.mark.hardware
def test_hardware_standard_event_status_is_readable(scope: DPO4054) -> None:
    """Verify basic SCPI status access through the active API session."""
    assert scope.scope is not None
    scope.scope.write("*CLS")
    esr = int(scope.scope.query("*ESR?").strip())
    assert esr == 0


@pytest.mark.hardware
def test_hardware_binary_waveform_transfer_is_deterministic(scope: DPO4054) -> None:
    """Validate the binary waveform API on a displayed analog channel.

    The default is intentionally modest for routine bench runs. Set
    ``DPO4000_WAVEFORM_POINTS`` to 10000, 100000, or a larger practical record
    length to execute the Phase-4 qualification matrix on the connected scope.
    """
    assert scope.scope is not None
    channel = int(os.getenv("DPO4000_TEST_CHANNEL", "1"))
    if not parse_channel_enabled(scope.scope.query(f"SELECT:CH{channel}?").strip()):
        pytest.skip(f"CH{channel} must be displayed for waveform transfer validation.")

    record_text = scope.scope.query("HORIZONTAL:RECORDLENGTH?").strip().split()[-1]
    record_length = int(float(record_text))
    requested = int(os.getenv("DPO4000_WAVEFORM_POINTS", "1000"))
    point_count = min(requested, record_length)
    if point_count <= 0:
        pytest.skip("Scope reported no waveform record points.")

    waveform = scope.read_channel_waveform_data(
        channel,
        start_index=1,
        point_count=point_count,
        encoding="RIBINARY",
        sample_width=2,
    )

    assert waveform.source == f"CH{channel}"
    assert waveform.start_index == 1
    assert waveform.stop_index == point_count
    assert waveform.sample_count == point_count
    assert waveform.preamble.record_point_count == point_count
    assert waveform.preamble.byte_width == 2
    assert waveform.preamble.binary_format == "RI"
    assert waveform.preamble.byte_order == "MSB"
    assert waveform.preamble.x_increment > 0
    assert math.isfinite(waveform.time_at(0))
    assert math.isfinite(waveform.time_at(waveform.sample_count - 1))
    assert math.isfinite(waveform.voltage_at(0))
    assert math.isfinite(waveform.voltage_at(waveform.sample_count - 1))


@pytest.mark.hardware
def test_hardware_partial_waveform_uses_outgoing_xzero(scope: DPO4054) -> None:
    """Exercise partial-transfer X-axis semantics on real DPO4000 firmware."""
    assert scope.scope is not None
    channel = int(os.getenv("DPO4000_TEST_CHANNEL", "1"))
    if not parse_channel_enabled(scope.scope.query(f"SELECT:CH{channel}?").strip()):
        pytest.skip(f"CH{channel} must be displayed for waveform transfer validation.")

    record_text = scope.scope.query("HORIZONTAL:RECORDLENGTH?").strip().split()[-1]
    record_length = int(float(record_text))
    if record_length < 3:
        pytest.skip("Waveform record is too short for partial-transfer validation.")

    point_count = min(10, record_length - 1)
    waveform = scope.read_channel_waveform_data(
        channel,
        start_index=2,
        point_count=point_count,
        encoding="RIBINARY",
        sample_width=2,
    )

    assert waveform.start_index == 2
    assert waveform.stop_index == point_count + 1
    assert waveform.sample_count == point_count
    assert waveform.preamble.record_point_count == point_count
    assert waveform.time_at(0) == pytest.approx(
        waveform.preamble.x_zero
        - waveform.preamble.point_offset * waveform.preamble.x_increment
    )
    if waveform.sample_count > 1:
        assert waveform.time_at(1) - waveform.time_at(0) == pytest.approx(
            waveform.preamble.x_increment
        )


@pytest.mark.hardware
def test_hardware_channel_label_write_round_trip(scope: DPO4054) -> None:
    """Optional write test: set and restore one channel label."""
    if not _env_enabled("DPO4000_ENABLE_WRITE_TESTS"):
        pytest.skip("Set DPO4000_ENABLE_WRITE_TESTS=1 to run label write round-trip test.")

    channel = int(os.getenv("DPO4000_TEST_CHANNEL", "1"))
    original_label = scope.get_channel_label(channel)
    test_label = os.getenv("DPO4000_TEST_LABEL", "API_TEST")[:30]

    try:
        scope.set_channel_label(channel, test_label)
        assert scope.get_channel_label(channel) == test_label
    finally:
        scope.set_channel_label(channel, original_label)
