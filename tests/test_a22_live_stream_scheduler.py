"""Deterministic A22 scheduler/concurrency regression without physical VISA."""
from array import array
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event, Lock
from time import monotonic

import pytest

from dpo4000_utils.live_stream import LiveStreamEngine, StreamConfig, StreamState, WaveformFrame


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def frame(token):
    from types import SimpleNamespace
    waveform = SimpleNamespace(sample_count=3, samples=array("h", [1, 2, 3]))
    return WaveformFrame(
        token[0], token[1], 0, datetime.now(timezone.utc), waveform, 0.27,
        (0.0, 1.0, 2.0), (1.0, 2.0, 3.0),
    )


def test_absolute_deadline_overrun_drops_two_deadlines():
    clock = Clock()
    engine = LiveStreamEngine(clock)
    engine.start(StreamConfig(target_hz=10))
    first = engine.begin_due()
    assert first is not None
    assert engine.begin_due() is None
    clock.advance(0.27)
    assert engine.complete(first, frame(first))
    assert engine.stats().deadlines_skipped == 2
    assert engine.due_in() == pytest.approx(0.03)
    clock.advance(0.03)
    second = engine.begin_due()
    assert second == (first[0], first[1] + 1)


def test_late_timer_skips_expired_intervals():
    clock = Clock()
    engine = LiveStreamEngine(clock)
    engine.start(StreamConfig(target_hz=10))
    clock.advance(0.45)
    assert engine.begin_due() is not None
    assert engine.stats().deadlines_skipped == 4


def test_latest_wins_and_render_is_separately_counted():
    clock = Clock()
    engine = LiveStreamEngine(clock)
    engine.start(StreamConfig(target_hz=10, buffer_frames=2))
    for i in range(10):
        token = engine.begin_due()
        assert token is not None
        assert engine.complete(token, frame(token))
        clock.advance(0.1)
    assert engine.pending_frames == 1
    assert engine.stats().frames_acquired == 10
    assert engine.stats().frames_replaced == 9
    assert engine.stats().frames_rendered == 0
    assert engine.take_latest().sequence == 10
    assert engine.take_latest() is None
    assert engine.stats().frames_rendered == 1


def test_pause_resume_discard_inflight_and_fresh_deadline():
    clock = Clock()
    engine = LiveStreamEngine(clock)
    engine.start()
    token = engine.begin_due()
    engine.pause()
    assert engine.state == StreamState.PAUSED
    assert engine.due_in() is None
    assert not engine.complete(token, frame(token))
    clock.advance(100)
    engine.resume()
    assert engine.due_in() == 0
    token2 = engine.begin_due()
    assert token2[0] != token[0]
    assert engine.complete(token2, frame(token2))


def test_stop_restart_stale_success_and_error_ignored():
    clock = Clock()
    engine = LiveStreamEngine(clock)
    engine.start()
    old = engine.begin_due()
    engine.stop()
    assert engine.state == StreamState.IDLE
    engine.start()
    assert engine.due_in() is None  # blocked old operation still owns the session
    assert not engine.complete(old, frame(old))
    assert engine.state == StreamState.STARTING
    new = engine.begin_due()
    assert new[0] != old[0]
    assert not engine.fail(old, TimeoutError("stale timeout"))
    assert engine.state == StreamState.RUNNING
    assert engine.complete(new, frame(new))
    assert engine.stats().acquisition_errors == 0


def test_errors_and_restart():
    engine = LiveStreamEngine(lambda: 0.0)
    engine.start()
    token = engine.begin_due()
    assert engine.fail(token, TimeoutError("VISA timeout"))
    assert engine.state is StreamState.ERROR
    assert "timeout" in engine.stats().last_error
    assert engine.stats().acquisition_errors == 1
    engine.start()
    assert engine.state is StreamState.STARTING


def test_real_blocking_fake_never_queues_second_operation():
    started = Event()
    release = Event()
    lock = Lock()
    active = [0, 0]

    def blocked_transfer():
        with lock:
            active[0] += 1
            active[1] = max(active)
        started.set()
        assert release.wait(2)
        with lock:
            active[0] -= 1
        return 1

    engine = LiveStreamEngine()
    engine.start(StreamConfig(target_hz=100))
    first = engine.begin_due()
    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(blocked_transfer)
        assert started.wait(2)
        before_stop = monotonic()
        for _ in range(1000):
            assert engine.begin_due() is None
        engine.stop()
        assert monotonic() - before_stop < 1
        engine.start()
        assert engine.begin_due() is None
        release.set()
        assert future.result(timeout=2) == 1
        assert not engine.complete(first, frame(first))
        assert engine.begin_due() is not None
    assert active[1] == 1


def test_pause_discards_unrendered_frame_and_keeps_render_count():
    clock = Clock()
    engine = LiveStreamEngine(clock)
    engine.start()
    token = engine.begin_due()
    assert engine.complete(token, frame(token))
    assert engine.pending_frames == 1
    engine.pause()
    assert engine.pending_frames == 0
    assert engine.take_latest() is None
    assert engine.stats().frames_rendered == 0
    engine.resume()
    assert engine.take_latest() is None


def test_old_frame_never_reappears_after_stop_restart():
    clock = Clock()
    engine = LiveStreamEngine(clock)
    engine.start()
    token = engine.begin_due()
    assert engine.complete(token, frame(token))
    engine.stop()
    engine.start()
    assert engine.take_latest() is None
    assert engine.stats().frames_rendered == 0
