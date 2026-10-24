"""Opt-in real DPO4054 A22 snapshot throughput qualification.

This test writes DATA:* transfer settings through the existing public driver.
Operator authorization and verified restoration are mandatory. It does not
reconfigure trigger/acquisition or claim lossless ADC streaming.
"""
from __future__ import annotations

import gc
import json
import os
import re
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dpo4000_utils import DPO4054
from dpo4000_utils.live_stream import (
    LiveStreamEngine, StreamConfig, StreamState, capture_frame,
)


_DATA_QUERIES = {
    "SOURCE": "DATA:SOURCE?",
    "START": "DATA:START?",
    "STOP": "DATA:STOP?",
    "WIDTH": "DATA:WIDTH?",
    "ENCDG": "DATA:ENCDG?",
}


def _data_setup(instrument) -> dict[str, str]:
    session = instrument.ensure_connected()
    values = {key: str(session.query(query)).strip().strip('"')
              for key, query in _DATA_QUERIES.items()}
    for key, value in values.items():
        if not re.fullmatch(r"[A-Za-z0-9]+", value):
            raise AssertionError(f"Unsafe or missing initial DATA:{key} response")
    if not all(values[key].isdigit() for key in ("START", "STOP", "WIDTH")):
        raise AssertionError("Invalid numeric DATA transfer setup")
    return values


def _restore_data_setup(instrument, initial: dict[str, str]) -> bool:
    session = instrument.ensure_connected()
    session.write(f"DATA:SOURCE {initial['SOURCE']}")
    session.write("DATA:START 1")
    session.write(f"DATA:STOP {initial['STOP']}")
    session.write(f"DATA:START {initial['START']}")
    session.write(f"DATA:WIDTH {initial['WIDTH']}")
    session.write(f"DATA:ENCDG {initial['ENCDG']}")
    return _data_setup(instrument) == initial


@pytest.fixture(scope="module")
def scope():
    if os.getenv("DPO4000_HARDWARE") != "1":
        pytest.skip("A22 DPO4054 HIL requires DPO4000_HARDWARE=1")
    for key in ("DPO4000_A22_REVERSIBLE_WRITES", "DPO4000_A22_EXCLUSIVE",
                "DPO4000_A22_RESTORE_APPROVED"):
        if os.getenv(key) != "YES":
            pytest.fail(f"Explicit operator authorization required: {key}=YES")
    resource = os.getenv("DPO4000_RESOURCE", "").strip()
    if not resource:
        pytest.fail("Set DPO4000_RESOURCE for explicit hardware qualification")
    if not os.getenv("DPO4000_A22_EVIDENCE_DIR", "").strip():
        pytest.fail("DPO4000_A22_EVIDENCE_DIR is required to retain HIL evidence")
    instrument = DPO4054(
        resource, auto_connect=False,
        timeout_ms=int(os.getenv("DPO4000_TIMEOUT_MS", "20000")),
    )
    initial = None
    identity = None
    instrument.connect()
    try:
        identity = instrument.query_identity()
        parts = [value.strip() for value in identity.upper().split(",")]
        assert len(parts) >= 4 and parts[0] == "TEKTRONIX" and parts[1] == "DPO4054", identity
        assert parts[2] and parts[3], "Scope serial number and firmware are required"
        expected = os.getenv("DPO4000_EXPECT_IDN", "TEKTRONIX,DPO4054").strip()
        assert expected and expected.upper() in identity.upper(), identity
        initial = _data_setup(instrument)
        yield instrument
    finally:
        verified = False
        restore_error = None
        try:
            if initial is not None:
                verified = _restore_data_setup(instrument, initial)
                if not verified:
                    restore_error = "DATA:* settings did not match initial snapshot"
        except Exception as exc:
            restore_error = f"{type(exc).__name__}: {exc}"
        finally:
            disconnect_error = None
            try:
                instrument.disconnect()
            except Exception as exc:
                disconnect_error = f"{type(exc).__name__}: {exc}"
            output_dir = os.getenv("DPO4000_A22_EVIDENCE_DIR", "").strip()
            if output_dir:
                folder = Path(output_dir)
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "a22-setup-restore.json").write_text(
                    json.dumps({
                        "kind": "dpo4054_data_setup_restoration",
                        "identity": identity, "initial": initial,
                        "verified": verified, "error": restore_error,
                        "disconnect_error": disconnect_error,
                        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                    }, indent=2) + "\n", encoding="utf-8"
                )
        if initial is not None and not verified:
            pytest.fail(f"CRITICAL: physical scope DATA setup restoration failed: {restore_error}")
        if disconnect_error:
            pytest.fail(f"CRITICAL: physical scope disconnect failed: {disconnect_error}")


@pytest.mark.hardware
@pytest.mark.parametrize("point_count", [1_000, 10_000, 100_000, 1_000_000])
def test_a22_read_only_sustained_snapshots(scope, point_count):
    selected = os.getenv("DPO4000_A22_POINT_COUNTS", "").strip()
    if selected:
        allowed = {int(v.strip()) for v in selected.split(",")}
        if point_count not in allowed:
            pytest.skip(f"A22 HIL point_count={point_count} excluded by opt-in selection")
    try:
        import psutil
    except ImportError:
        pytest.fail("A22 hardware metrics require psutil for RSS measurements")
    process = psutil.Process()
    gc.collect()
    rss_before = process.memory_info().rss
    tracing_started_here = not tracemalloc.is_tracing()
    if tracing_started_here:
        tracemalloc.start()
    allocated_before, _ = tracemalloc.get_traced_memory()
    rss_peak = rss_before
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
        rss_peak = max(rss_peak, process.memory_info().rss)
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
    allocated_after, allocated_peak = tracemalloc.get_traced_memory()
    if tracing_started_here:
        tracemalloc.stop()
    rss_after = process.memory_info().rss
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
        "identity": scope.query_identity(),
        "commit_sha": os.getenv("GITHUB_SHA"),
        "rss_initial_bytes": rss_before,
        "rss_final_bytes": rss_after,
        "rss_peak_bytes": rss_peak,
        "rss_growth_bytes": rss_after - rss_before,
        "python_alloc_growth_bytes": allocated_after - allocated_before,
        "python_alloc_peak_over_initial_bytes": allocated_peak - allocated_before,
    }
    output_dir = os.getenv("DPO4000_A22_EVIDENCE_DIR", "").strip()
    if output_dir:
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"a22-{transport.split('/')[0].lower()}-{point_count}.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
    assert result.acquisition_errors == 0


@pytest.mark.hardware
def test_a22_stop_during_real_transfer_discards_late_frame(scope):
    """Real VISA call finishes before querying again; no competing scope I/O."""
    config = StreamConfig(point_count=10_000, target_hz=5.0)
    engine = LiveStreamEngine()
    engine.start(config)
    token = engine.begin_due()
    assert token is not None
    entered = Event()

    def read_on_single_worker():
        entered.set()
        return capture_frame(scope, config, *token)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(read_on_single_worker)
        assert entered.wait(2), "Physical worker did not start"
        engine.stop()
        assert engine.in_flight  # Stop invalidates publication, not VISA ownership.
        frame = future.result(timeout=90)  # No concurrent SCPI access.
    assert not engine.complete(token, frame)
    assert engine.state is StreamState.IDLE
    assert not engine.in_flight and engine.take_latest() is None
    assert "DPO4054" in scope.query_identity().upper()


@pytest.mark.hardware
def test_a22_pause_resume_real_scope_transfer(scope):
    config = StreamConfig(point_count=10_000, target_hz=5.0)
    engine = LiveStreamEngine()
    engine.start(config)
    first = engine.begin_due()
    assert first is not None
    frame1 = capture_frame(scope, config, *first)
    assert engine.complete(first, frame1)
    assert engine.pending_frames == 1
    engine.pause()
    assert engine.state is StreamState.PAUSED
    assert engine.pending_frames == 0 and engine.take_latest() is None
    engine.resume()
    second = engine.begin_due()
    assert second is not None and second[0] != first[0]
    frame2 = capture_frame(scope, config, *second)
    assert engine.complete(second, frame2)
    assert engine.take_latest() is not None
    engine.stop()
    assert "DPO4054" in scope.query_identity().upper()
