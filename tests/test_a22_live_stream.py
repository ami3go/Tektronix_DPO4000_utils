"""A22 model, validation, min/max and public driver-boundary tests."""
from array import array
from datetime import datetime, timezone

import pytest

from dpo4000_utils.live_stream import (
    LiveStreamEngine, StreamConfig, StreamState, capture_frame, minmax_indices,
    prepare_render,
)
from dpo4000_utils.waveform import WaveformData, WaveformPreamble


def waveform(samples=None):
    raw = array("h", samples if samples is not None else range(1000))
    preamble = WaveformPreamble(
        byte_width=2, encoding="BINARY", binary_format="RI", byte_order="MSB",
        record_point_count=len(raw), point_format="Y", x_unit="s",
        x_increment=0.001, x_zero=-0.1, point_offset=0,
        y_unit="V", y_multiplier=0.01, y_offset=0, y_zero=0,
    )
    return WaveformData(
        source="CH1", label="", start_index=1, stop_index=len(raw),
        requested_encoding="RIBINARY", preamble=preamble,
        samples=raw, acquired_at=datetime.now(timezone.utc),
    )


@pytest.mark.parametrize("override", [
    {"source": "MATH"}, {"source": "CH5"}, {"source": "ch1"},
    {"point_count": 0}, {"point_count": -1}, {"point_count": True},
    {"point_count": 1_000_001}, {"target_hz": 0}, {"target_hz": -1},
    {"target_hz": float("nan")}, {"target_hz": float("inf")},
    {"target_hz": 101}, {"render_points": 99}, {"render_points": 50_001},
    {"buffer_frames": 0}, {"buffer_frames": 9}, {"reconnect": True},
])
def test_invalid_config(override):
    with pytest.raises(ValueError):
        StreamConfig(**override)


def test_default_acceptance_configuration():
    config = StreamConfig()
    assert (config.source, config.point_count, config.target_hz, config.render_points) == (
        "CH1", 10_000, 5.0, 2_000
    )
    assert StreamConfig(point_count=None, target_hz=100, buffer_frames=8)


@pytest.mark.parametrize("n", [0, 1, 100, 2000, 2001, 1_000_000])
def test_minmax_budget_extrema_and_order(n):
    raw = array("h", [0]) * n
    if n > 5:
        raw[n // 2] = 32767
        raw[(n // 2) + 1] = -32768
    indices = minmax_indices(raw, 2000)
    assert len(indices) <= 2000
    assert tuple(sorted(set(indices))) == indices
    if n:
        assert indices[0] == 0
        assert indices[-1] == n - 1
        if n > 2000:
            assert n // 2 in indices
            assert n // 2 + 1 in indices


def test_prepare_render_has_correct_scaling():
    wf = waveform(range(3000))
    x, y = prepare_render(wf, 200)
    assert len(x) == len(y) <= 200
    assert x[0] == pytest.approx(-0.1)
    assert y[-1] == pytest.approx(29.99)


def test_public_driver_api_only():
    class Fake:
        def __init__(self):
            self.called = []

        def read_channel_waveform_data(self, channel, *, point_count):
            self.called.append((channel, point_count))
            return waveform()

    fake = Fake()
    frame = capture_frame(fake, StreamConfig(), 11, 2)
    assert fake.called == [(1, 10_000)]
    assert (frame.generation, frame.sequence) == (11, 2)
    assert len(frame.render_x) <= 2000
    assert frame.acquired_monotonic_s >= 0
    assert frame.acquired_wall_time.tzinfo is not None


def test_invalid_state_transitions():
    engine = LiveStreamEngine()
    with pytest.raises(RuntimeError):
        engine.resume()
    with pytest.raises(RuntimeError):
        engine.pause()
    engine.start()
    with pytest.raises(RuntimeError):
        engine.start()
    engine.pause()
    assert engine.state is StreamState.PAUSED
    engine.resume()
    assert engine.state is StreamState.STARTING
    engine.stop()
    assert engine.state is StreamState.IDLE
