#!/usr/bin/env python3
"""Capture synthetic A18 bundle creation/verification scaling evidence."""

from __future__ import annotations

import argparse
from array import array
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import tempfile
import time

from dpo4000_utils.evidence import create_evidence_bundle, verify_evidence_bundle
from dpo4000_utils.recipe import RecipeResult, RecipeRunState, StepResult
from dpo4000_utils.waveform import WaveformData, WaveformPreamble

PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0bIDAT\x08\xd7c\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb1"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def _summary(values: list[float]) -> dict[str, float | int]:
    return {
        "sample_count": len(values),
        "min": min(values),
        "p50": statistics.median(values),
        "p95": _percentile(values, 0.95),
        "p99": _percentile(values, 0.99),
        "max": max(values),
    }


def _recipe() -> RecipeResult:
    return RecipeResult(
        "A18 benchmark",
        RecipeRunState.COMPLETED,
        0.0,
        0.001,
        (StepResult(0, "value", 1, 0.0, 0.001, 1.0),),
    )


def _waveform(count: int) -> WaveformData:
    preamble = WaveformPreamble(
        byte_width=2,
        encoding="BINARY",
        binary_format="RI",
        byte_order="MSB",
        record_point_count=count,
        point_format="Y",
        x_unit="s",
        x_increment=1e-6,
        x_zero=0.0,
        point_offset=0.0,
        y_unit="V",
        y_multiplier=0.001,
        y_offset=0.0,
        y_zero=0.0,
    )
    samples = array("h", ((index % 20_000) - 10_000 for index in range(count)))
    return WaveformData(
        source="CH1",
        label="benchmark",
        start_index=1,
        stop_index=count,
        requested_encoding="RIBINARY",
        preamble=preamble,
        samples=samples,
        acquired_at=datetime.now(timezone.utc),
    )


def benchmark(sizes: list[int], repetitions: int) -> dict:
    cases = []
    with tempfile.TemporaryDirectory(prefix="a18-benchmark-") as temp_dir:
        root = Path(temp_dir)
        for size in sizes:
            waveform = _waveform(size)
            create_times: list[float] = []
            verify_times: list[float] = []
            finalize_times: list[float] = []
            bundle_sizes: list[int] = []
            for repetition in range(repetitions):
                output = root / f"a18-{size}-{repetition}.dpoe"
                result = create_evidence_bundle(
                    output,
                    recipe_result=_recipe(),
                    screen_png=PNG,
                    waveforms={"CH1": waveform},
                    metadata={"benchmark_points": size},
                )
                started = time.perf_counter()
                verified = verify_evidence_bundle(output)
                verify_times.append(time.perf_counter() - started)
                create_times.append(result.metrics.total_s)
                finalize_times.append(result.metrics.finalize_s)
                bundle_sizes.append(result.size_bytes)
                assert verified.bundle_sha256 == result.sha256
            median_create = statistics.median(create_times)
            cases.append(
                {
                    "points": size,
                    "create_s": _summary(create_times),
                    "verify_s": _summary(verify_times),
                    "atomic_finalize_s": _summary(finalize_times),
                    "bundle_size_bytes": int(statistics.median(bundle_sizes)),
                    "samples_per_s": size / median_create if median_create else 0.0,
                }
            )
    return {
        "schema": "a18-evidence-benchmark",
        "version": 1,
        "repetitions": repetitions,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default="1000,10000,100000,1000000")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sizes = [int(item.strip()) for item in args.sizes.split(",") if item.strip()]
    if not sizes or any(value <= 0 for value in sizes):
        parser.error("--sizes must contain positive integers")
    if args.repetitions <= 0:
        parser.error("--repetitions must be positive")
    report = benchmark(sizes, args.repetitions)
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
