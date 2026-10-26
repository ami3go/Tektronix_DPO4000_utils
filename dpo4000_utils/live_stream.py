"""A22 bounded waveform-snapshot streaming; no Qt or VISA dependencies.

The caller owns scheduling and the one serialized scope session. The model never
queues I/O. One pending complete frame plus one active transfer is the memory
bound; rendering consumers may drop frames deliberately.
"""
from __future__ import annotations

import math
import time
from array import array
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from .waveform import PreambleCache, WaveformData, validate_waveform_alignment

try:
    import numpy as _np  # optional speedup; core API works without NumPy
except ImportError:  # pragma: no cover - exercised in driver-only environments
    _np = None

MAX_POINTS = 1_000_000
MAX_FRAME_BUFFER = 8


class StreamState(str, Enum):
    IDLE = "IDLE"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class StreamConfig:
    # ``source`` remains as a compatibility alias for callers that select one
    # channel. New code should use ``sources``; __post_init__ normalizes both.
    source: str = "CH1"
    point_count: int | None = None
    target_hz: float = 5.0
    render_points: int = 2_000
    buffer_frames: int = 2
    reconnect: bool = False
    sources: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        selected = (self.source,) if self.sources is None else self.sources
        if isinstance(selected, str) or not isinstance(selected, (tuple, list)):
            raise ValueError("A22 sources must be an ordered channel sequence")
        normalized = tuple(selected)
        if not normalized:
            raise ValueError("A22 requires at least one source")
        if len(normalized) > 4 or len(set(normalized)) != len(normalized):
            raise ValueError("A22 sources must contain 1..4 unique channels")
        if any(
            not isinstance(channel, str)
            or channel not in {"CH1", "CH2", "CH3", "CH4"}
            for channel in normalized
        ):
            raise ValueError("A22 sources must be selected from CH1..CH4")
        object.__setattr__(self, "sources", normalized)
        object.__setattr__(self, "source", normalized[0])
        # ``None`` reads the record exactly as the scope is set up; the driver
        # rejects a record above MAX_POINTS before CURVE? is issued.
        if self.point_count is not None and (
            type(self.point_count) is not int or not 1 <= self.point_count <= MAX_POINTS
        ):
            raise ValueError("point_count must be None (scope setup) or 1..1,000,000")
        if isinstance(self.target_hz, bool) or not isinstance(
            self.target_hz, (int, float)
        ) or not math.isfinite(self.target_hz) or not 0 < self.target_hz <= 100:
            raise ValueError("target_hz must be finite and in (0,100]")
        if type(self.render_points) is not int or not 100 <= self.render_points <= 50_000:
            raise ValueError("render_points must be 100..50,000")
        if type(self.buffer_frames) is not int or not 1 <= self.buffer_frames <= MAX_FRAME_BUFFER:
            raise ValueError("buffer_frames must be 1..8")
        if type(self.reconnect) is not bool:
            raise ValueError("reconnect must be boolean")
        if self.reconnect:
            raise ValueError("A22 v1 automatic reconnect is not supported; restart manually")


@dataclass(frozen=True)
class WaveformFrame:
    generation: int
    sequence: int
    acquired_monotonic_s: float
    acquired_wall_time: datetime
    waveform: WaveformData
    acquisition_duration_s: float
    render_x: tuple[float, ...]
    render_y: tuple[float, ...]
    decimation_duration_s: float = 0.0


@dataclass(frozen=True)
class WaveformGroup:
    """One complete sequential acquisition cycle for the selected channels.

    The group is published atomically. Individual frames retain their own
    acquisition timestamps so the UI can report, rather than hide, channel skew.
    """

    generation: int
    sequence: int
    acquired_monotonic_s: float
    acquired_wall_time: datetime
    frames: tuple[WaveformFrame, ...]
    acquisition_duration_s: float
    channel_skew_s: float

    @property
    def sources(self) -> tuple[str, ...]:
        return tuple(frame.waveform.source for frame in self.frames)

    @property
    def sample_count(self) -> int:
        return sum(frame.waveform.sample_count for frame in self.frames)

    @property
    def byte_count(self) -> int:
        return sum(
            frame.waveform.sample_count * frame.waveform.samples.itemsize
            for frame in self.frames
        )

    @property
    def channel_durations_s(self) -> tuple[tuple[str, float], ...]:
        return tuple(
            (frame.waveform.source, frame.acquisition_duration_s)
            for frame in self.frames
        )


@dataclass(frozen=True)
class StreamStats:
    generation: int
    frames_acquired: int
    frames_rendered: int
    frames_replaced: int
    deadlines_skipped: int
    acquisition_errors: int
    reconnect_count: int
    acquisition_fps: float
    render_fps: float
    latest_acquisition_s: float
    p50_acquisition_s: float
    p95_acquisition_s: float
    p99_acquisition_s: float
    transfer_samples_per_s: float
    transfer_bytes_per_s: float
    last_error: str | None
    channel_count: int = 1
    latest_channel_skew_s: float = 0.0
    latest_channel_durations_s: tuple[tuple[str, float], ...] = ()


def minmax_indices(samples: array, budget: int) -> tuple[int, ...]:
    """Select deterministic original indices; narrow positive/negative spikes survive.

    Indices 0 and N-1 are always retained. No full-length float conversion or
    intermediate O(N) index list is made when decimating large records.
    """
    size = len(samples)
    if size <= budget:
        return tuple(range(size))
    if budget < 4:
        raise ValueError("Decimation budget must be at least four")
    buckets = (budget - 2) // 2
    result = [0]
    interior = size - 2
    # NumPy is available in the Desk extra and avoids slow Python indexing
    # over a 1M-sample record. frombuffer is zero-copy for array storage.
    fast_view = None
    if _np is not None and samples.typecode in {"b", "B", "h", "H", "i", "I", "f", "d"}:
        fast_view = _np.frombuffer(samples, dtype=_np.dtype(samples.typecode))
    for bucket in range(buckets):
        lo = 1 + bucket * interior // buckets
        hi = 1 + (bucket + 1) * interior // buckets
        if fast_view is not None:
            subset = fast_view[lo:hi]  # zero-copy view, no full-record copies
            first_min = lo + int(subset.argmin())
            first_max = lo + int(subset.argmax())
        else:
            first_min = first_max = lo
            for index in range(lo + 1, hi):
                if samples[index] < samples[first_min]:
                    first_min = index
                if samples[index] > samples[first_max]:
                    first_max = index
        if first_min == first_max:
            result.append(first_min)
        else:
            result.extend(sorted((first_min, first_max)))
    result.append(size - 1)
    return tuple(result)


def prepare_render(waveform: WaveformData, budget: int) -> tuple[tuple[float, ...], tuple[float, ...]]:
    p = waveform.preamble
    indices = minmax_indices(waveform.samples, budget)
    xs = tuple(p.x_zero + (i - p.point_offset) * p.x_increment for i in indices)
    ys = tuple(
        (waveform.samples[i] - p.y_offset) * p.y_multiplier + p.y_zero
        for i in indices
    )
    return xs, ys


def capture_frame(
    scope: object,
    config: StreamConfig,
    generation: int,
    sequence: int,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> WaveformFrame:
    """Call only the public driver API; run on the existing scope worker."""
    if config.sources != (config.source,):
        raise ValueError("capture_frame requires exactly one selected source")
    started = clock()
    waveform = scope.read_channel_waveform_data(
        int(config.source[2:]), **_transfer_limits(config)
    )
    end = clock()
    if not isinstance(waveform, WaveformData) or not waveform.sample_count:
        raise ValueError("Scope returned an empty or malformed WaveformData")
    if waveform.sample_count > MAX_POINTS:
        raise ValueError("Scope returned more than A22's 1,000,000-sample retention limit")
    if waveform.source != config.source:
        raise ValueError("Scope returned the wrong waveform source")
    render_start = clock()
    x, y = prepare_render(waveform, config.render_points)
    decimation_seconds = max(0.0, clock() - render_start)
    return WaveformFrame(
        generation=generation,
        sequence=sequence,
        acquired_monotonic_s=end,
        acquired_wall_time=datetime.now(timezone.utc),
        waveform=waveform,
        acquisition_duration_s=max(0.0, end - started),
        render_x=x,
        render_y=y,
        decimation_duration_s=decimation_seconds,
    )


def _transfer_limits(
    config: StreamConfig, preamble_cache: PreambleCache | None = None,
) -> dict[str, object]:
    """Driver keywords: an explicit count, or the scope's own record with a size cap."""
    limits: dict[str, object] = (
        {"point_count": None, "max_points": MAX_POINTS}
        if config.point_count is None else {"point_count": config.point_count}
    )
    if preamble_cache is not None:
        limits["preamble_cache"] = preamble_cache
    return limits


def capture_group(
    scope: object,
    config: StreamConfig,
    generation: int,
    sequence: int,
    *,
    clock: Callable[[], float] = time.monotonic,
    preamble_cache: PreambleCache | None = None,
) -> WaveformGroup:
    """Acquire selected channels sequentially and publish one validated group.

    Each transfer uses the public driver method. No partial result escapes this
    function: a failed source or incompatible X axis fails the complete cycle.
    """
    started = clock()
    frames: list[WaveformFrame] = []
    if preamble_cache is not None:
        preamble_cache.begin_cycle()
    # A source that is not displayed makes WFMOUTPRE? fail with no reply (error
    # 2244), which surfaces only as a VISA timeout. Fail fast and name the cause.
    list_enabled = getattr(scope, "_enabled_channel_numbers", None)
    if callable(list_enabled):
        shown = {f"CH{number}" for number in list_enabled()}
        hidden = [source for source in config.sources or () if source not in shown]
        if hidden:
            raise ValueError(
                f"{', '.join(hidden)} not displayed on the scope; turn the channel on "
                "or deselect it (A22 never changes channel state)"
            )
    for source in config.sources or ():
        channel_started = clock()
        waveform = scope.read_channel_waveform_data(
            int(source[2:]), **_transfer_limits(config, preamble_cache)
        )
        channel_end = clock()
        if not isinstance(waveform, WaveformData) or not waveform.sample_count:
            raise ValueError(f"Scope returned an empty or malformed WaveformData for {source}")
        if waveform.sample_count > MAX_POINTS:
            raise ValueError(
                f"Scope returned more than A22's 1,000,000-sample retention limit for {source}"
            )
        if waveform.source != source:
            raise ValueError(
                f"Scope returned {waveform.source or 'an unknown source'} while {source} was requested"
            )
        render_start = clock()
        x, y = prepare_render(waveform, config.render_points)
        frames.append(WaveformFrame(
            generation=generation,
            sequence=sequence,
            acquired_monotonic_s=channel_end,
            acquired_wall_time=datetime.now(timezone.utc),
            waveform=waveform,
            acquisition_duration_s=max(0.0, channel_end - channel_started),
            render_x=x,
            render_y=y,
            decimation_duration_s=max(0.0, clock() - render_start),
        ))

    if not frames:
        raise ValueError("A22 acquired no channels")
    validate_waveform_alignment([frame.waveform for frame in frames])
    completed = clock()
    channel_times = [frame.acquired_monotonic_s for frame in frames]
    return WaveformGroup(
        generation=generation,
        sequence=sequence,
        acquired_monotonic_s=completed,
        acquired_wall_time=datetime.now(timezone.utc),
        frames=tuple(frames),
        acquisition_duration_s=max(0.0, completed - started),
        channel_skew_s=max(channel_times) - min(channel_times),
    )


def _percentile(values: deque[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


class LiveStreamEngine:
    """Qt-free absolute-deadline, single-flight, latest-frame stream state.

    Public methods run on the single completion/scheduler owner thread. Blocking
    VISA work executes elsewhere; its completion must call complete() or fail()
    even after Stop, to release the physical in-flight lease.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self.state = StreamState.IDLE
        self.generation = 0
        self.config = StreamConfig()
        self._busy_token: tuple[int, int] | None = None
        self._deadline: float | None = None
        self._pending: WaveformFrame | WaveformGroup | None = None
        self._started_at = clock()
        self._sequence = 0
        self._acquired = 0
        self._rendered = 0
        self._replaced = 0
        self._skipped = 0
        self._errors = 0
        self._samples = 0
        self._bytes = 0
        self._latencies: deque[float] = deque(maxlen=512)
        self._latest_acquisition = 0.0
        self._latest_channel_count = 1
        self._latest_channel_skew = 0.0
        self._latest_channel_durations: tuple[tuple[str, float], ...] = ()
        self.last_error: str | None = None

    @property
    def in_flight(self) -> bool:
        return self._busy_token is not None

    @property
    def pending_frames(self) -> int:
        return int(self._pending is not None)

    def start(self, config: StreamConfig | None = None) -> int:
        if self.state not in {StreamState.IDLE, StreamState.ERROR}:
            raise RuntimeError(f"Cannot start from {self.state.value}")
        self.config = config or self.config
        self.generation += 1
        self.state = StreamState.STARTING
        self._deadline = self._clock()
        self._pending = None
        self._sequence = 0
        self._started_at = self._clock()
        # Per-run counters reset even if a stopped prior generation still owns
        # the physical transfer; its eventual callback cannot count here.
        self._acquired = self._rendered = self._replaced = 0
        self._skipped = self._errors = self._samples = self._bytes = 0
        self._latencies.clear()
        self._latest_acquisition = 0.0
        self._latest_channel_count = len(self.config.sources or ())
        self._latest_channel_skew = 0.0
        self._latest_channel_durations = ()
        self.last_error = None
        return self.generation

    def pause(self) -> None:
        if self.state not in {StreamState.STARTING, StreamState.RUNNING}:
            raise RuntimeError("Cannot pause a nonrunning stream")
        self.generation += 1  # discard completion that was already in flight
        self.state = StreamState.PAUSED
        self._deadline = None
        self._pending = None  # Never paint a pre-Pause frame afterward.

    def resume(self) -> None:
        if self.state is not StreamState.PAUSED:
            raise RuntimeError("Cannot resume unless paused")
        self.generation += 1
        self.state = StreamState.STARTING
        self._deadline = self._clock()  # no replay or catch-up

    def stop(self) -> None:
        self.generation += 1
        self._deadline = None
        self._pending = None
        self.state = StreamState.IDLE

    def due_in(self) -> float | None:
        if self.state not in {StreamState.STARTING, StreamState.RUNNING}:
            return None
        if self.in_flight or self._deadline is None:
            return None
        return max(0.0, self._deadline - self._clock())

    def begin_due(self) -> tuple[int, int] | None:
        if self.due_in() is None or self.in_flight:
            return None
        now = self._clock()
        if self._deadline is None or now < self._deadline:
            return None
        period = 1.0 / self.config.target_hz
        # A delayed Qt tick also skips expired absolute intervals.
        late = max(0, math.floor((now - self._deadline) / period))
        self._skipped += late
        self._deadline += (late + 1) * period
        self._sequence += 1
        token = (self.generation, self._sequence)
        self._busy_token = token
        self.state = StreamState.RUNNING
        return token

    def _release(self, token: tuple[int, int]) -> bool:
        if token != self._busy_token:
            return False
        self._busy_token = None
        # Advance over all expired future deadlines after a slow transfer.
        if self._deadline is not None and self.state in {
            StreamState.STARTING, StreamState.RUNNING
        } and token[0] == self.generation:
            period = 1.0 / self.config.target_hz
            now = self._clock()
            if now >= self._deadline:
                missed = math.floor((now - self._deadline) / period) + 1
                self._skipped += missed
                self._deadline += missed * period
        return token[0] == self.generation

    def complete(
        self, token: tuple[int, int], frame: WaveformFrame | WaveformGroup
    ) -> bool:
        current = self._release(token)
        if not current or self.state is not StreamState.RUNNING:
            return False
        if (frame.generation, frame.sequence) != token:
            self._errors += 1
            self.last_error = "Acquisition frame identity mismatch"
            self.state = StreamState.ERROR
            return False
        self._acquired += 1
        self._latest_acquisition = frame.acquisition_duration_s
        self._latencies.append(frame.acquisition_duration_s)
        if isinstance(frame, WaveformGroup):
            self._samples += frame.sample_count
            self._bytes += frame.byte_count
            self._latest_channel_count = len(frame.frames)
            self._latest_channel_skew = frame.channel_skew_s
            self._latest_channel_durations = frame.channel_durations_s
        else:
            self._samples += frame.waveform.sample_count
            self._bytes += frame.waveform.sample_count * frame.waveform.samples.itemsize
            self._latest_channel_count = 1
            self._latest_channel_skew = 0.0
            self._latest_channel_durations = ((
                getattr(frame.waveform, "source", self.config.source),
                frame.acquisition_duration_s,
            ),)
        if self._pending is not None:
            self._replaced += 1
        self._pending = frame
        return True

    def fail(self, token: tuple[int, int], error: BaseException) -> bool:
        if not self._release(token) or self.state is not StreamState.RUNNING:
            return False
        self._errors += 1
        self.last_error = f"{type(error).__name__}: {error}"
        self.state = StreamState.ERROR
        self._deadline = None
        self._pending = None
        return True

    def take_latest(self) -> WaveformFrame | WaveformGroup | None:
        frame = self._pending
        self._pending = None
        if (
            frame is None
            or self.state is not StreamState.RUNNING
            or frame.generation != self.generation
        ):
            return None
        self._rendered += 1
        return frame

    def stats(self) -> StreamStats:
        elapsed = max(1e-9, self._clock() - self._started_at)
        return StreamStats(
            generation=self.generation, frames_acquired=self._acquired,
            frames_rendered=self._rendered, frames_replaced=self._replaced,
            deadlines_skipped=self._skipped, acquisition_errors=self._errors,
            reconnect_count=0, acquisition_fps=self._acquired / elapsed,
            render_fps=self._rendered / elapsed,
            latest_acquisition_s=self._latest_acquisition,
            p50_acquisition_s=_percentile(self._latencies, 0.5),
            p95_acquisition_s=_percentile(self._latencies, 0.95),
            p99_acquisition_s=_percentile(self._latencies, 0.99),
            transfer_samples_per_s=self._samples / elapsed,
            transfer_bytes_per_s=self._bytes / elapsed,
            last_error=self.last_error,
            channel_count=self._latest_channel_count,
            latest_channel_skew_s=self._latest_channel_skew,
            latest_channel_durations_s=self._latest_channel_durations,
        )


__all__ = [
    "StreamConfig", "StreamState", "StreamStats", "WaveformFrame", "WaveformGroup",
    "LiveStreamEngine", "capture_frame", "capture_group", "minmax_indices",
    "prepare_render",
]
