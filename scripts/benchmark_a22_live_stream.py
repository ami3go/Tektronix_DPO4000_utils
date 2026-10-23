#!/usr/bin/env python3
"""Synthetic A22 decimation/backpressure benchmark (NOT DPO4054 throughput)."""
from __future__ import annotations

import argparse
import json
import time
import tracemalloc
from array import array
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from dpo4000_utils.live_stream import (
    LiveStreamEngine, StreamConfig, WaveformFrame, minmax_indices,
)


def percentile(values, q):
    ordered = sorted(values)
    k = (len(ordered) - 1) * q
    i = int(k)
    return ordered[i] + (ordered[min(i + 1, len(ordered) - 1)] - ordered[i]) * (k - i)


def benchmark_size(size: int, iterations: int, budget: int) -> dict:
    samples = array("h", [0]) * size
    samples[size // 3] = 32767
    samples[(2 * size) // 3] = -32768
    durations = []
    tracemalloc.start()
    base_current, base_peak = tracemalloc.get_traced_memory()
    for _ in range(iterations):
        began = time.perf_counter()
        indices = minmax_indices(samples, budget)
        durations.append(time.perf_counter() - began)
    now_current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert indices[0] == 0 and indices[-1] == size - 1
    assert size // 3 in indices and 2 * size // 3 in indices

    # Synthetic producer is deliberately faster than consumer: latest wins.
    tick = [0.0]
    stream = LiveStreamEngine(lambda: tick[0])
    stream.start(StreamConfig(point_count=size, render_points=budget, target_hz=100))
    waveform = SimpleNamespace(sample_count=size, samples=samples)
    handoff_times = []
    stat_times = []
    for _ in range(iterations):
        began = time.perf_counter()
        token = stream.begin_due()
        assert token is not None
        stream.complete(token, WaveformFrame(
            token[0], token[1], tick[0], datetime.now(timezone.utc),
            waveform, 0.0001, (0.0,), (0.0,),
        ))
        handoff_times.append(time.perf_counter() - began)
        began = time.perf_counter()
        stream.stats()
        stat_times.append(time.perf_counter() - began)
        tick[0] += 0.01
    summary = stream.stats()
    return {
        "requested_samples": size,
        "render_budget": budget,
        "rendered_samples": len(indices),
        "raw_bytes": size * samples.itemsize,
        "decimation_seconds": {
            "p50": percentile(durations, .5),
            "p95": percentile(durations, .95),
            "p99": percentile(durations, .99),
            "max": max(durations),
        },
        "frame_handoff_seconds": {"p50": percentile(handoff_times, .5),
                                   "p95": percentile(handoff_times, .95),
                                   "p99": percentile(handoff_times, .99),
                                   "max": max(handoff_times)},
        "stats_update_seconds": {"p50": percentile(stat_times, .5),
                                  "p95": percentile(stat_times, .95),
                                  "p99": percentile(stat_times, .99),
                                  "max": max(stat_times)},
        "tracemalloc_additional_peak_bytes": max(0, peak - base_current),
        "tracemalloc_additional_current_bytes": max(0, now_current - base_current),
        "synthetic_frames_acquired": summary.frames_acquired,
        "synthetic_frames_replaced": summary.frames_replaced,
        "synthetic_frames_rendered": summary.frames_rendered,
        "synthetic_deadlines_skipped": summary.deadlines_skipped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", default="1000,10000,100000,1000000")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--render-points", type=int, default=2000)
    parser.add_argument("--output", type=Path, default=Path("a22-synthetic-benchmark.json"))
    args = parser.parse_args()
    if not 1 <= args.iterations <= 1000:
        parser.error("--iterations must be 1..1000")
    if not 100 <= args.render_points <= 50_000:
        parser.error("--render-points must be 100..50000")
    allowed = {1000, 10000, 100000, 1000000}
    sizes = [int(s) for s in args.sizes.split(",")]
    if not sizes or not set(sizes) <= allowed:
        parser.error("--sizes must be a comma-separated subset of 1000,10000,100000,1000000")
    result = {
        "kind": "synthetic_only_not_instrument_performance",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "iterations": args.iterations,
        "render_points": args.render_points,
        "cases": [benchmark_size(n, args.iterations, args.render_points) for n in sizes],
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
