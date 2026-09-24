"""Compare a candidate R0-F/R0-T capture against the committed baseline.

Implements the comparison policy from ``docs/regression-test-plan.md``:

- functional (R0-F): any change to normalized public behavior is reported (section 16 -
  "must not silently change established functional behavior"); metadata fields that
  legitimately differ every run (commit SHA, timestamp, etc.) are excluded.
- timing (R0-T): section 4.4's relative-AND-absolute gate,
  ``candidate_p95 > baseline_p95 * relative_limit AND candidate_p95 - baseline_p95 >
  absolute_tolerance``, evaluated per operation against ``tests/baselines/r0_timing_thresholds.json``.

This module never writes to the baseline files themselves - updating the baseline stays a
separate, explicit ``scripts/capture_r0_baseline.py`` run (section 16).
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Any

FUNCTIONAL_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "schema_version",
        "commit_sha",
        "captured_at",
        "package_version",
        "python",
        "platform",
        "resource",
        "idn",
        "firmware",
    }
)

# Leaf paths that hold live, signal-dependent readings rather than stable configuration.
# These are expected to differ between captures whenever the connected signal differs and
# are not a functional regression by themselves - unlike everything else in the functional
# snapshot, which represents configuration/behavior that should be stable across runs.
FUNCTIONAL_VOLATILE_PATH_PATTERNS: tuple[str, ...] = ("measurements.*.value",)

DEFAULT_RELATIVE_LIMIT = 1.30


def _is_volatile_path(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


@dataclass(frozen=True)
class FunctionalDiff:
    path: str
    kind: str  # "changed", "added", "removed"
    baseline: Any = None
    candidate: Any = None


@dataclass(frozen=True)
class OperationThreshold:
    absolute_tolerance_s: float
    relative_limit: float = DEFAULT_RELATIVE_LIMIT


@dataclass(frozen=True)
class TimingRegression:
    operation: str
    metric: str
    baseline_value: float
    candidate_value: float
    relative_limit: float
    absolute_tolerance_s: float
    relative_exceeded: bool
    absolute_exceeded: bool

    @property
    def regressed(self) -> bool:
        return self.relative_exceeded and self.absolute_exceeded


def diff_functional(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    volatile_path_patterns: tuple[str, ...] = FUNCTIONAL_VOLATILE_PATH_PATTERNS,
) -> list[FunctionalDiff]:
    """Report every normalized-behavior difference, ignoring per-run metadata fields and
    known-volatile leaf paths (live signal readings, not configuration)."""
    diffs: list[FunctionalDiff] = []
    _diff_node(
        baseline,
        candidate,
        path=(),
        diffs=diffs,
        top_level=True,
        volatile_path_patterns=volatile_path_patterns,
    )
    return diffs


def _diff_node(
    baseline: Any,
    candidate: Any,
    *,
    path: tuple[str, ...],
    diffs: list[FunctionalDiff],
    volatile_path_patterns: tuple[str, ...],
    top_level: bool = False,
) -> None:
    if isinstance(baseline, dict) and isinstance(candidate, dict):
        keys = sorted(set(baseline) | set(candidate))
        for key in keys:
            if top_level and key in FUNCTIONAL_METADATA_KEYS:
                continue
            child_path = (*path, str(key))
            if key not in candidate:
                diffs.append(FunctionalDiff(".".join(child_path), "removed", baseline=baseline[key]))
            elif key not in baseline:
                diffs.append(FunctionalDiff(".".join(child_path), "added", candidate=candidate[key]))
            else:
                _diff_node(
                    baseline[key],
                    candidate[key],
                    path=child_path,
                    diffs=diffs,
                    volatile_path_patterns=volatile_path_patterns,
                )
        return
    if baseline != candidate:
        joined_path = ".".join(path)
        if _is_volatile_path(joined_path, volatile_path_patterns):
            return
        diffs.append(FunctionalDiff(joined_path, "changed", baseline=baseline, candidate=candidate))


def _flatten_operations(operations: dict[str, Any]) -> dict[str, dict[str, float]]:
    flat: dict[str, dict[str, float]] = {}
    for name, value in operations.items():
        if name == "not_yet_covered":
            continue
        if name == "waveform_acquisition" and isinstance(value, dict):
            for size, stats in value.items():
                if isinstance(stats, dict) and "p95" in stats:
                    flat[f"waveform_acquisition.{size}"] = stats
            continue
        if isinstance(value, dict) and "p95" in value:
            flat[name] = value
    return flat


def diff_timing(
    baseline_operations: dict[str, Any],
    candidate_operations: dict[str, Any],
    thresholds: dict[str, OperationThreshold],
    *,
    default_threshold: OperationThreshold | None = None,
    metric: str = "p95",
) -> tuple[list[TimingRegression], list[str], list[str]]:
    """Compare every operation present on both sides; return (regressions, new, missing)."""
    baseline_flat = _flatten_operations(baseline_operations)
    candidate_flat = _flatten_operations(candidate_operations)

    common = sorted(set(baseline_flat) & set(candidate_flat))
    new_operations = sorted(set(candidate_flat) - set(baseline_flat))
    missing_operations = sorted(set(baseline_flat) - set(candidate_flat))

    regressions: list[TimingRegression] = []
    for operation in common:
        threshold = thresholds.get(operation, default_threshold)
        if threshold is None:
            continue
        baseline_value = baseline_flat[operation][metric]
        candidate_value = candidate_flat[operation][metric]
        relative_exceeded = candidate_value > baseline_value * threshold.relative_limit
        absolute_exceeded = (candidate_value - baseline_value) > threshold.absolute_tolerance_s
        regressions.append(
            TimingRegression(
                operation=operation,
                metric=metric,
                baseline_value=baseline_value,
                candidate_value=candidate_value,
                relative_limit=threshold.relative_limit,
                absolute_tolerance_s=threshold.absolute_tolerance_s,
                relative_exceeded=relative_exceeded,
                absolute_exceeded=absolute_exceeded,
            )
        )
    return regressions, new_operations, missing_operations


def load_thresholds(payload: dict[str, Any]) -> dict[str, OperationThreshold]:
    """Parse a thresholds JSON payload (see tests/baselines/r0_timing_thresholds.json)."""
    thresholds: dict[str, OperationThreshold] = {}
    for operation, entry in payload.get("operations", {}).items():
        thresholds[operation] = OperationThreshold(
            absolute_tolerance_s=float(entry["absolute_tolerance_s"]),
            relative_limit=float(entry.get("relative_limit", DEFAULT_RELATIVE_LIMIT)),
        )
    return thresholds


def regression_exit_code(
    functional_diffs: list[FunctionalDiff],
    timing_regressions: list[TimingRegression],
) -> int:
    if functional_diffs:
        return 1
    if any(regression.regressed for regression in timing_regressions):
        return 1
    return 0
