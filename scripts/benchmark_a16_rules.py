#!/usr/bin/env python3
"""Synthetic A16 rule-engine throughput and latency benchmark.

Shared-CI output is smoke evidence only. Authoritative p95/p99 limits belong on the
controlled regression runner described in docs/regression-test-plan.md.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import time

from dpo4000_utils.rules import (
    MAX_RULE_NODES,
    CompareOperator,
    LogicOperator,
    RuleEngine,
    RuleGroup,
    RuleSet,
    ScalarRule,
)


def _parse_sizes(value: str) -> tuple[int, ...]:
    result = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    if not result or any(size <= 0 for size in result):
        raise argparse.ArgumentTypeError("sizes must be positive comma-separated integers")
    return result


def _build_rule_set(leaves: int) -> RuleSet:
    """One AND group over ``leaves`` always-passing compare rules (leaves + 1 nodes)."""
    if not 1 <= leaves <= MAX_RULE_NODES - 1:
        raise ValueError(f"leaves must be in range 1..{MAX_RULE_NODES - 1}")
    rules = [
        ScalarRule(f"r{i}", f"MEAS{i % 8 + 1}", CompareOperator.INSIDE, low=-1e9, high=1e9, unit="V")
        for i in range(leaves)
    ]
    root_group = RuleGroup(id="root", logic=LogicOperator.AND, children=tuple(rules))
    return RuleSet(name="rules", root=root_group)


def _percentile(sorted_values: list[float], fraction: float) -> float:
    """Calculate percentile using nearest-rank method."""
    index = min(len(sorted_values) - 1, max(0, math.ceil(fraction * len(sorted_values)) - 1))
    return sorted_values[index]


def benchmark(leaves: int, *, evaluations: int) -> dict[str, object]:
    values = {f"MEAS{n}": float(n) for n in range(1, 9)}
    engine = RuleEngine()
    rule_set = _build_rule_set(leaves)

    # One warm-up run
    engine.evaluate(rule_set, values)

    durations = []
    for _ in range(evaluations):
        start = time.perf_counter()
        result = engine.evaluate(rule_set, values)
        duration = time.perf_counter() - start
        durations.append(duration)

        if result.status.value != "PASS":
            raise RuntimeError("benchmark rule set did not pass")

    total_duration = sum(durations)

    return {
        "leaves": leaves,
        "nodes": leaves + 1,
        "evaluations": evaluations,
        "median_s": statistics.median(durations),
        "p95_s": _percentile(sorted(durations), 0.95),
        "p99_s": _percentile(sorted(durations), 0.99),
        "max_s": max(durations),
        "rules_per_second": leaves * evaluations / total_duration,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sizes",
        type=_parse_sizes,
        default=(10, 100, 1_000, MAX_RULE_NODES - 1),
        help="comma-separated leaf counts per rule tree",
    )
    parser.add_argument("--evaluations", type=int, default=200)
    parser.add_argument("--output", type=Path, default=Path("a16-rule-benchmark.json"))
    args = parser.parse_args()
    if args.evaluations < 1:
        parser.error("--evaluations must be >= 1")
    if any(size > MAX_RULE_NODES - 1 for size in args.sizes):
        parser.error(f"--sizes entries must be <= {MAX_RULE_NODES - 1}")

    payload = {
        "kind": "A16 shared-runner smoke benchmark",
        "authoritative_baseline": False,
        "cases": [
            benchmark(leaves, evaluations=args.evaluations)
            for leaves in args.sizes
        ],
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
