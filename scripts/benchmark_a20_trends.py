#!/usr/bin/env python3
"""Synthetic A20 trend-model scaling benchmark.

Shared-CI output is smoke evidence only. Authoritative p50/p95/p99 and GUI-heartbeat
limits belong on the controlled regression runner described in docs/regression-test-plan.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import time
import tracemalloc

from dpo4000_utils.trend import MeasurementTrendModel


def _parse_sizes(value: str) -> tuple[int, ...]:
    result = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    if not result or any(size <= 0 for size in result):
        raise argparse.ArgumentTypeError("sizes must be positive comma-separated integers")
    return result


def benchmark(size: int, *, render_points: int, repetitions: int) -> dict[str, object]:
    append_runs: list[float] = []
    decimate_runs: list[float] = []
    peak_bytes = 0
    for _ in range(repetitions):
        model = MeasurementTrendModel(capacity=size)
        tracemalloc.start()
        started = time.perf_counter()
        for index in range(size):
            model.append("MEAS1", float(index % 1000), timestamp_s=float(index))
        append_s = time.perf_counter() - started
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_bytes = max(peak_bytes, peak)

        started = time.perf_counter()
        snapshot = model.snapshot("MEAS1", max_points=render_points)
        decimate_s = time.perf_counter() - started
        if snapshot.count > render_points:
            raise RuntimeError("decimation exceeded requested render budget")
        append_runs.append(append_s)
        decimate_runs.append(decimate_s)

    return {
        "size": size,
        "render_points": render_points,
        "repetitions": repetitions,
        "append_median_s": statistics.median(append_runs),
        "append_samples_per_second": size / statistics.median(append_runs),
        "decimate_median_s": statistics.median(decimate_runs),
        "peak_traced_python_bytes": peak_bytes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=_parse_sizes, default=(1_000, 10_000, 100_000))
    parser.add_argument("--render-points", type=int, default=2_000)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("a20-trend-benchmark.json"))
    args = parser.parse_args()
    if args.render_points < 2:
        parser.error("--render-points must be >= 2")
    if args.repetitions < 1:
        parser.error("--repetitions must be >= 1")

    payload = {
        "kind": "A20 shared-runner smoke benchmark",
        "authoritative_baseline": False,
        "cases": [
            benchmark(size, render_points=args.render_points, repetitions=args.repetitions)
            for size in args.sizes
        ],
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
