"""Opt-in A14 Advanced Trigger qualification against a real DPO4000-family scope."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator

import pytest

from dpo4000_utils import DPO4054
from dpo4000_utils.connection import visaResourceAddr


_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


@pytest.fixture(scope="module")
def a14_scope() -> Iterator[DPO4054]:
    if not _env_enabled("DPO4000_HARDWARE"):
        pytest.skip("Set DPO4000_HARDWARE=1 to run A14 hardware qualification.")
    resource = os.getenv("DPO4000_RESOURCE", visaResourceAddr).strip()
    if not resource:
        pytest.skip("Set DPO4000_RESOURCE to the oscilloscope VISA resource.")
    instrument = DPO4054(
        resource,
        auto_connect=False,
        timeout_ms=int(os.getenv("DPO4000_TIMEOUT_MS", "20000")),
    )
    instrument.connect()
    try:
        yield instrument
    finally:
        instrument.disconnect()


@pytest.mark.hardware
def test_a14_verified_holdoff_query_is_supported_and_probe_restores_timeout(a14_scope: DPO4054) -> None:
    assert a14_scope.scope is not None
    original_timeout = a14_scope.scope.timeout
    probe_timeout_ms = int(os.getenv("DPO4000_A14_PROBE_TIMEOUT_MS", "500"))
    result = a14_scope.probe_scpi_query("TRIGGER:A:HOLDOFF:VALUE?", timeout_ms=probe_timeout_ms)
    assert result.supported is True
    assert result.timed_out is False
    assert result.response
    assert result.elapsed_s < max(2.0, probe_timeout_ms / 1000.0 * 3.0)
    assert a14_scope.scope.timeout == original_timeout


@pytest.mark.hardware
def test_a14_known_unsupported_b_events_mode_probe_is_bounded_and_recovers(a14_scope: DPO4054) -> None:
    """Reproduce the A14 hang candidate without inheriting the normal VISA timeout."""
    assert a14_scope.scope is not None
    original_timeout = a14_scope.scope.timeout
    probe_timeout_ms = int(os.getenv("DPO4000_A14_PROBE_TIMEOUT_MS", "500"))
    started = time.monotonic()
    result = a14_scope.probe_scpi_query("TRIGGER:B:EVENTS:MODE?", timeout_ms=probe_timeout_ms)
    elapsed = time.monotonic() - started
    assert result.supported is False
    assert result.recovered is True
    assert elapsed < max(2.0, probe_timeout_ms / 1000.0 * 3.0)
    assert a14_scope.scope.timeout == original_timeout

    idn = a14_scope.query_identity().upper()
    if "DPO4054" in idn:
        # This exact firmware path was live-reproduced during A14.7 qualification.
        assert result.timed_out is True


@pytest.mark.hardware
def test_a14_holdoff_write_readback_is_reversible(a14_scope: DPO4054) -> None:
    if not _env_enabled("DPO4000_ENABLE_WRITE_TESTS"):
        pytest.skip("Set DPO4000_ENABLE_WRITE_TESTS=1 for reversible A14 write qualification.")

    original = a14_scope.get_trigger_holdoff()
    try:
        written = a14_scope.set_trigger_holdoff(original)
        assert written == pytest.approx(original)
    finally:
        a14_scope.set_trigger_holdoff(original, verify=False)
    assert a14_scope.get_trigger_holdoff() == pytest.approx(original)
