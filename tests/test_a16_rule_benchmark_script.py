from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("benchmark_a16_rules", ROOT / "scripts" / "benchmark_a16_rules.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_benchmark_case_reports_throughput_and_percentiles():
    case = module.benchmark(50, evaluations=20)
    assert case["nodes"] == 51
    assert case["rules_per_second"] > 0
    assert 0 < case["median_s"] <= case["p95_s"] <= case["p99_s"] <= case["max_s"]


def test_percentile_nearest_rank():
    values = [1.0, 2.0, 3.0, 4.0]
    assert module._percentile(values, 0.5) == 2.0
    assert module._percentile(values, 0.95) == 4.0
    assert module._percentile(values, 0.0) == 1.0


def test_main_writes_json(tmp_path, monkeypatch):
    out = tmp_path / "output.json"
    monkeypatch.setattr(sys, "argv", ["x", "--sizes", "5", "--evaluations", "3", "--output", str(out)])
    assert module.main() == 0
    data = json.loads(out.read_text())
    assert data["authoritative_baseline"] is False
    assert data["cases"][0]["leaves"] == 5


@pytest.mark.parametrize("leaves", [0, 10_000])
def test_rule_tree_size_is_validated_not_clamped(leaves):
    with pytest.raises(ValueError):
        module._build_rule_set(leaves)
