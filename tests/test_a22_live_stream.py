"""A22 model, validation, min/max and public driver-boundary tests."""
from array import array
from datetime import datetime, timezone

import pytest

from dpo4000_utils.live_stream import (
    LiveStreamEngine, StreamConfig, StreamState, WaveformGroup, capture_frame,
    capture_group, minmax_indices, prepare_render,
)
from dpo4000_utils.waveform import WaveformData, WaveformPreamble


def waveform(samples=None, *, source="CH1", x_increment=0.001):
    raw = array("h", samples if samples is not None else range(1000))
    preamble = WaveformPreamble(
        byte_width=2, encoding="BINARY", binary_format="RI", byte_order="MSB",
        record_point_count=len(raw), point_format="Y", x_unit="s",
        x_increment=x_increment, x_zero=-0.1, point_offset=0,
        y_unit="V", y_multiplier=0.01, y_offset=0, y_zero=0,
    )
    return WaveformData(
        source=source, label="", start_index=1, stop_index=len(raw),
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
    {"sources": ()}, {"sources": ("CH1", "CH1")},
    {"sources": ("CH1", "CH2", "CH3", "CH4", "CH1")},
    {"sources": ("CH1", "MATH")},
])
def test_invalid_config(override):
    with pytest.raises(ValueError):
        StreamConfig(**override)


def test_default_acceptance_configuration():
    config = StreamConfig()
    assert (config.source, config.point_count, config.target_hz, config.render_points) == (
        "CH1", None, 5.0, 2_000
    )
    assert StreamConfig(point_count=1_000_000, target_hz=100, buffer_frames=8)
    multi = StreamConfig(sources=("CH1", "CH2", "CH3", "CH4"))
    assert multi.sources == ("CH1", "CH2", "CH3", "CH4")
    assert multi.source == "CH1"  # compatibility alias


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

        def read_channel_waveform_data(self, channel, *, point_count, max_points=None):
            self.called.append((channel, point_count))
            return waveform()

    fake = Fake()
    frame = capture_frame(fake, StreamConfig(), 11, 2)
    assert fake.called == [(1, None)]
    assert (frame.generation, frame.sequence) == (11, 2)
    assert len(frame.render_x) <= 2000
    assert frame.acquired_monotonic_s >= 0
    assert frame.acquired_wall_time.tzinfo is not None


def test_four_channel_group_is_complete_ordered_and_counted():
    class Fake:
        def __init__(self):
            self.called = []

        def read_channel_waveform_data(self, channel, *, point_count, max_points=None):
            self.called.append((channel, point_count))
            return waveform(source=f"CH{channel}")

    fake = Fake()
    config = StreamConfig(sources=("CH1", "CH2", "CH3", "CH4"))
    group = capture_group(fake, config, 7, 9)
    assert isinstance(group, WaveformGroup)
    assert group.sources == ("CH1", "CH2", "CH3", "CH4")
    assert fake.called == [(1, None), (2, None), (3, None), (4, None)]
    assert group.sample_count == 4_000
    assert group.byte_count == 8_000
    engine = LiveStreamEngine(lambda: 0.0)
    engine.start(config)
    token = engine.begin_due()
    equivalent = WaveformGroup(
        token[0], token[1], group.acquired_monotonic_s, group.acquired_wall_time,
        tuple(
            type(frame)(
                token[0], token[1], frame.acquired_monotonic_s,
                frame.acquired_wall_time, frame.waveform,
                frame.acquisition_duration_s, frame.render_x, frame.render_y,
                frame.decimation_duration_s,
            )
            for frame in group.frames
        ),
        group.acquisition_duration_s, group.channel_skew_s,
    )
    assert engine.complete(token, equivalent)
    assert engine.stats().channel_count == 4
    assert isinstance(engine.take_latest(), WaveformGroup)


def test_four_channel_group_rejects_partial_or_misaligned_cycle():
    class Partial:
        def read_channel_waveform_data(self, channel, *, point_count, max_points=None):
            if channel == 3:
                raise TimeoutError("CH3 transfer failed")
            return waveform(source=f"CH{channel}")

    config = StreamConfig(sources=("CH1", "CH2", "CH3", "CH4"))
    with pytest.raises(TimeoutError, match="CH3"):
        capture_group(Partial(), config, 1, 1)

    class Misaligned:
        def read_channel_waveform_data(self, channel, *, point_count, max_points=None):
            return waveform(
                source=f"CH{channel}",
                x_increment=0.002 if channel == 4 else 0.001,
            )

    with pytest.raises(Exception, match="mismatch"):
        capture_group(Misaligned(), config, 1, 1)


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


def test_minmax_pure_python_fallback_preserves_spikes(monkeypatch):
    import dpo4000_utils.live_stream as stream

    monkeypatch.setattr(stream, "_np", None)
    samples = array("h", [0]) * 10_000
    samples[2203], samples[8507] = 32767, -32768
    indices = minmax_indices(samples, 200)
    assert (2203 in indices) and (8507 in indices)
    assert len(indices) <= 200
    assert indices[0] == 0 and indices[-1] == 9999


def test_scope_setup_read_passes_a_size_cap_instead_of_a_count():
    class Fake:
        def read_channel_waveform_data(self, channel, *, point_count, max_points=None):
            assert point_count is None and max_points == 1_000_000
            return waveform([0, 1, 2])

    assert capture_frame(Fake(), StreamConfig(), 1, 1).waveform.sample_count == 3


def test_oversized_driver_return_is_rejected_even_for_bounded_request():
    class OversizedFake:
        def read_channel_waveform_data(self, channel, *, point_count, max_points=None):
            return waveform([0] * 1_000_001)

    with pytest.raises(ValueError, match="retention limit"):
        capture_frame(OversizedFake(), StreamConfig(point_count=1_000_000), 1, 1)


def test_capture_group_rejects_hidden_channels_before_any_transfer():
    class Fake:
        called: list = []

        def _enabled_channel_numbers(self):
            return [1]

        def read_channel_waveform_data(self, channel, **kwargs):
            self.called.append(channel)
            raise AssertionError("must not transfer a hidden channel")

    fake = Fake()
    config = StreamConfig(sources=("CH1", "CH2", "CH4"))
    with pytest.raises(ValueError, match="CH2, CH4 not displayed"):
        capture_group(fake, config, 1, 1)
    assert fake.called == []
