"""Opt-in real DPO4054 A22 snapshot throughput qualification.

This test sends only existing driver's DATA transfer configuration and queries.
It does not reconfigure trigger/acquisition or claim lossless ADC streaming.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dpo4000_utils import DPO4054
from dpo4000_utils.live_stream import (
    LiveStreamEngine, StreamConfig, StreamState, capture_frame,
)


@pytest.fixture(scope="module")
def scope():
    if os.getenv("DPO4000_HARDWARE") != "1":
        pytest.skip("A22 DPO4054 HIL requires DPO4000_HARDWARE=1")
    resource = os.getenv("DPO4000_RESOURCE", "").strip()
    if not resource:
        pytest.skip("Set DPO4000_RESOURCE for explicit hardware qualification")
    instrument = DPO4054(
        resource, auto_connect=False,
        timeout_ms=int(os.getenv("DPO4000_TIMEOUT_MS", "20000")),
    )
    instrument.connect()
    try:
        identity = instrument.query_identity()
        expected = os.getenv("DPO4000_EXPECT_IDN", "TEKTRONIX,DPO4054")
        assert expected.upper() in identity.upper(), identity
        yield instrument
    finally:
        instrument.disconnect()


@pytest.mark.hardware
@pytest.mark.parametrize("point_count", [1_000, 10_000, 100_000, 1_000_000])
def test_a22_read_only_sustained_snapshots(scope, point_count):
    selected = os.getenv("DPO4000_A22_POINT_COUNTS", "").strip()
    if selected:
        allowed = {int(v.strip()) for v in selected.split(",")}
        if point_count not in allowed:
            pytest.skip(f"A22 HIL point_count={point_count} excluded by opt-in selection")
    seconds = max(1, int(os.getenv("DPO4000_A22_RUN_SECONDS", "30")))
    target_hz = float(os.getenv("DPO4000_A22_TARGET_HZ", "5"))
    config = StreamConfig(point_count=point_count, target_hz=target_hz)
    engine = LiveStreamEngine()
    generation = engine.start(config)
    deadline = time.monotonic() + seconds
    previous_timestamp = None
    frames_observed = 0
    max_in_flight = 0
    while time.monotonic() < deadline:
        delay = engine.due_in()
        if delay is None:
            raise AssertionError("A22 HIL scheduler unexpectedly lost acquisition eligibility")
        if delay:
            time.sleep(min(delay, 0.05))
            continue
        token = engine.begin_due()
        assert token is not None
        assert not engine.begin_due()  # no second transfer while one is outstanding
        max_in_flight = max(max_in_flight, int(engine.in_flight))
        try:
            frame = capture_frame(scope, config, *token)
        except Exception as exc:
            engine.fail(token, exc)
            raise
        assert engine.complete(token, frame)
        assert frame.waveform.sample_count == point_count
        assert frame.waveform.preamble.record_point_count == point_count
        assert frame.waveform.preamble.x_increment > 0
        assert frame.generation == generation
        assert frame.sequence == frames_observed + 1
        if previous_timestamp is not None:
            assert frame.acquired_monotonic_s >= previous_timestamp
        previous_timestamp = frame.acquired_monotonic_s
        frames_observed += 1
        engine.take_latest()
        assert engine.pending_frames <= 1
    assert max_in_flight == 1 and frames_observed > 0
    result = engine.stats()
    engine.stop()
    assert engine.state is StreamState.IDLE and not engine.in_flight
    assert "DPO4054" in scope.query_identity().upper()
    # A real Stop/Restart must leave the retained public driver session usable.
    engine.start(config)
    token = engine.begin_due()
    assert token is not None
    frame = capture_frame(scope, config, *token)
    assert engine.complete(token, frame)
    engine.stop()
    resource = os.getenv("DPO4000_RESOURCE", "")
    transport = "USB" if resource.upper().startswith("USB") else (
        "TCPIP/VXI-11" if resource.upper().startswith("TCPIP") else "OTHER"
    )
    payload = {
        "kind": "real_dpo4054_hil",
        "point_count": point_count, "transport": transport, "target_hz": target_hz,
        "run_seconds": seconds, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "actual_fps": result.acquisition_fps,
        "p50_s": result.p50_acquisition_s, "p95_s": result.p95_acquisition_s,
        "p99_s": result.p99_acquisition_s,
        "samples_per_second": result.transfer_samples_per_s,
        "payload_mb_per_second": result.transfer_bytes_per_s / 1e6,
        "deadlines_skipped": result.deadlines_skipped,
        "frames_replaced": result.frames_replaced,
        "errors": result.acquisition_errors,
        "max_in_flight": max_in_flight,
    }
    output_dir = os.getenv("DPO4000_A22_EVIDENCE_DIR", "").strip()
    if output_dir:
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"a22-{transport.split('/')[0].lower()}-{point_count}.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
    assert result.acquisition_errors == 0
