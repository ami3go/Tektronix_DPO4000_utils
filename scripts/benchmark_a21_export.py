#!/usr/bin/env python3
"""Benchmark A21 export/import throughput and peak Python memory.

The harness is intentionally synthetic so it can run on controlled CI/performance
hosts without a scope. Hardware waveform acquisition remains a separate HIL metric.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
import tracemalloc
from array import array
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dpo4000_utils.scientific_export import (
    ScientificFormat,
    export_scientific_dataset,
    import_scientific_dataset,
)
from dpo4000_utils.waveform import WaveformData, WaveformPreamble


def synthetic_waveform(points: int) -> WaveformData:
    samples = array("h", ((index % 2000) - 1000 for index in range(points)))
    return WaveformData(
        source="CH1",
        label="Synthetic",
        start_index=1,
        stop_index=points,
        requested_encoding="RIBINARY",
        preamble=WaveformPreamble(
            byte_width=2,
            encoding="BINARY",
            binary_format="RI",
            byte_order="MSB",
            record_point_count=points,
            point_format="Y",
            x_unit="s",
            x_increment=1e-6,
            x_zero=-0.001,
            point_offset=0.0,
            y_unit="V",
            y_multiplier=0.001,
            y_offset=0.0,
            y_zero=0.0,
        ),
        samples=samples,
        acquired_at=datetime.now(timezone.utc),
    )


def _measure(callable_obj):
    tracemalloc.start()
    started = time.perf_counter()
    value = callable_obj()
    duration = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return value, duration, peak


def benchmark_case(
    output_dir: Path,
    *,
    points: int,
    export_format: ScientificFormat,
    compressed: bool,
) -> dict[str, Any]:
    waveform = synthetic_waveform(points)
    suffix = ".npz" if export_format is ScientificFormat.NPZ else ".dpoz"
    path = output_dir / f"a21_{points}_{export_format.value}{suffix}"

    exported, export_wall_s, export_peak = _measure(
        lambda: export_scientific_dataset(
            path,
            [waveform],
            format=export_format,
            compressed=compressed,
            metadata={"benchmark": True, "points": points},
        )
    )
    imported, import_wall_s, import_peak = _measure(
        lambda: import_scientific_dataset(path)
    )
    round_trip = imported.dataset.waveforms[0]
    exact = (
        round_trip.preamble == waveform.preamble
        and round_trip.samples.typecode == waveform.samples.typecode
        and round_trip.samples == waveform.samples
    )
    return {
        "format": export_format.value,
        "compressed": compressed,
        "points": points,
        "file_bytes": path.stat().st_size,
        "export": {
            "wall_s": export_wall_s,
            "reported_s": exported.duration_s,
            "samples_per_second": exported.samples_per_second,
            "megabytes_per_second": exported.megabytes_per_second,
            "peak_python_bytes": export_peak,
        },
        "import": {
            "wall_s": import_wall_s,
            "reported_s": imported.duration_s,
            "samples_per_second": imported.samples_per_second,
            "peak_python_bytes": import_peak,
        },
        "round_trip_exact": exact,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sizes",
        default="1000,10000,100000,1000000",
        help="Comma-separated sample counts.",
    )
    parser.add_argument(
        "--formats",
        default="npz,dpoz",
        help="Comma-separated formats: npz,dpoz.",
    )
    parser.add_argument("--compressed", action="store_true")
    parser.add_argument("--output", type=Path, help="Optional JSON report path.")
    parser.add_argument("--keep-files", action="store_true")
    args = parser.parse_args()

    sizes = [int(value.strip()) for value in args.sizes.split(",") if value.strip()]
    if not sizes or any(value <= 0 for value in sizes):
        parser.error("--sizes must contain positive integers")
    formats = [
        ScientificFormat(value.strip().lower())
        for value in args.formats.split(",")
        if value.strip()
    ]
    if not formats:
        parser.error("--formats must contain npz and/or dpoz")

    temporary = None
    if args.keep_files:
        output_dir = Path("a21_export_benchmark")
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="a21-export-")
        output_dir = Path(temporary.name)

    try:
        cases = [
            benchmark_case(
                output_dir,
                points=points,
                export_format=export_format,
                compressed=args.compressed,
            )
            for export_format in formats
            for points in sizes
        ]
        report = {
            "schema": "a21-scientific-export-benchmark",
            "version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "cases": cases,
        }
        text = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        print(text, end="")
        return 0 if all(case["round_trip_exact"] for case in cases) else 2
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
