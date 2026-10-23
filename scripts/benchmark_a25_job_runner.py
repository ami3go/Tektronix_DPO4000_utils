#!/usr/bin/env python3
"""Synthetic A25 headless-job timing benchmark.

Shared-CI output is smoke evidence only. Controlled runners own authoritative
process-start, p50/p95/p99, cancellation, and shutdown baselines.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import statistics
from tempfile import TemporaryDirectory
import time

from dpo4000_utils.job_runner import HeadlessJobRunner, JobConfig, JobExitCode, write_job_report
from dpo4000_utils.recipe import RecipeSequencer, recipe_from_mapping


class FakeScope:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def query_identity(self) -> str:
        return "TEKTRONIX,DPO4054,FAKE,0"

    def read_value(self, value: float = 1.0) -> float:
        return float(value)


@contextmanager
def fake_session(_resource, **_kwargs):
    yield FakeScope()


def _recipe_document(step_count: int) -> dict[str, object]:
    return {
        "version": 1,
        "name": f"benchmark {step_count}",
        "steps": [
            {
                "kind": "call",
                "name": f"value-{index}",
                "method": "read_value",
                "args": [float(index)],
            }
            for index in range(step_count)
        ],
    }


def _duration_stats(callback, repetitions: int) -> dict[str, float]:
    durations: list[float] = []
    for _ in range(repetitions):
        started = time.perf_counter()
        callback()
        durations.append(time.perf_counter() - started)
    return {
        "median_s": statistics.median(durations),
        "p95_s": (
            statistics.quantiles(durations, n=100, method="inclusive")[94]
            if repetitions >= 2 else durations[0]
        ),
    }


def benchmark(step_count: int, repetitions: int) -> dict[str, float | int]:
    with TemporaryDirectory(prefix="a25-bench-") as directory:
        recipe_path = Path(directory) / "recipe.json"
        document = _recipe_document(step_count)
        recipe_path.write_text(json.dumps(document), encoding="utf-8")
        recipe = recipe_from_mapping(document)

        runner = HeadlessJobRunner(
            session_factory=fake_session,
            validation_target_factory=FakeScope,
        )
        validate_config = JobConfig(recipe_path=recipe_path, validate_only=True)
        run_config = JobConfig(recipe_path=recipe_path, resource="FAKE::INSTR")

        validation = _duration_stats(
            lambda: _require_success(runner.run(validate_config)), repetitions
        )
        complete = _duration_stats(
            lambda: _require_success(runner.run(run_config)), repetitions
        )
        direct = _duration_stats(
            lambda: _require_recipe_success(RecipeSequencer(FakeScope()).run(recipe)),
            repetitions,
        )
        successful = runner.run(run_config)
        _require_success(successful)
        report_file = Path(directory) / "report.json"
        reporting = _duration_stats(
            lambda: write_job_report(report_file, successful), repetitions
        )

    return {
        "step_count": step_count,
        "repetitions": repetitions,
        "validation_median_s": validation["median_s"],
        "validation_p95_s": validation["p95_s"],
        "job_median_s": complete["median_s"],
        "job_p95_s": complete["p95_s"],
        "direct_sequencer_median_s": direct["median_s"],
        "direct_sequencer_p95_s": direct["p95_s"],
        "report_write_median_s": reporting["median_s"],
        "report_write_p95_s": reporting["p95_s"],
        "job_overhead_s": complete["median_s"] - direct["median_s"],
        "job_steps_per_second": (
            step_count / complete["median_s"] if complete["median_s"] > 0 else 0.0
        ),
    }


def _require_success(result) -> None:
    if result.exit_code is not JobExitCode.SUCCESS:
        raise RuntimeError(f"headless benchmark failed: {result.status}: {result.message}")


def _require_recipe_success(result) -> None:
    if result.state.value != "completed":
        raise RuntimeError(f"direct sequencer benchmark failed: {result}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", default="1,100,1000")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("a25-job-benchmark.json"))
    args = parser.parse_args()
    steps = tuple(int(value.strip()) for value in args.steps.split(",") if value.strip())
    if not steps or any(value <= 0 for value in steps):
        parser.error("--steps must contain positive comma-separated integers")
    if args.repetitions < 1:
        parser.error("--repetitions must be >= 1")

    payload = {
        "kind": "A25 shared-runner smoke benchmark",
        "authoritative_baseline": False,
        "cases": [benchmark(count, args.repetitions) for count in steps],
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
