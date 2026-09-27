from __future__ import annotations

import pytest

from dpo4000_utils.regression import (
    PerformanceGate,
    TimingSummary,
    linear_slope,
    percentile,
    summarize_timings,
)


def test_timing_summary_records_required_r0_distribution() -> None:
    summary = summarize_timings([0.0, 1.0, 2.0, 3.0, 4.0])
    assert summary == TimingSummary(
        minimum=0.0,
        p50=2.0,
        p95=3.8,
        p99=3.96,
        maximum=4.0,
        sample_count=5,
    )


def test_percentile_is_stable_for_one_sample_and_unsorted_input() -> None:
    assert percentile([4.0], 0.99) == 4.0
    assert percentile([3.0, 1.0, 2.0], 0.50) == 2.0


@pytest.mark.parametrize(
    "samples",
    ([], [float("nan")], [float("inf")], [-0.001]),
)
def test_timing_summary_rejects_invalid_samples(samples) -> None:
    with pytest.raises(ValueError):
        summarize_timings(samples)


def test_performance_gate_requires_relative_and_absolute_regression() -> None:
    baseline = TimingSummary(0.05, 0.08, 0.10, 0.12, 0.15, 100)
    gate = PerformanceGate(relative_limit=1.30, absolute_tolerance=0.05)

    # >30% slower but only +40 ms: shared-host noise allowance keeps it passing.
    candidate_relative_only = TimingSummary(0.06, 0.10, 0.14, 0.15, 0.18, 100)
    assert not gate.failed(baseline=baseline, candidate=candidate_relative_only)

    # +60 ms and >30% slower: both gates are exceeded, therefore fail.
    candidate_both = TimingSummary(0.07, 0.12, 0.16, 0.18, 0.20, 100)
    assert gate.failed(baseline=baseline, candidate=candidate_both)

    # Absolute change is large enough, but relative limit is not exceeded.
    slow_baseline = TimingSummary(1.0, 1.0, 1.0, 1.0, 1.0, 100)
    candidate_absolute_only = TimingSummary(1.0, 1.1, 1.2, 1.2, 1.2, 100)
    assert not gate.failed(baseline=slow_baseline, candidate=candidate_absolute_only)


def test_linear_slope_detects_growth_flat_and_decline() -> None:
    assert linear_slope([1, 2, 3, 4, 5]) == pytest.approx(1.0)
    assert linear_slope([7, 7, 7, 7]) == pytest.approx(0.0)
    assert linear_slope([5, 4, 3, 2, 1]) == pytest.approx(-1.0)
    assert linear_slope([42]) == 0.0


def test_performance_gate_validation() -> None:
    with pytest.raises(ValueError):
        PerformanceGate(relative_limit=0.99)
    with pytest.raises(ValueError):
        PerformanceGate(absolute_tolerance=-0.001)
