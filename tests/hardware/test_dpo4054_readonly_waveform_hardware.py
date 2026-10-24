"""Physical DPO4054 query-only waveform/evidence/export HIL (opt in)."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

from dpo4000_utils import DPO4054
from dpo4000_utils.evidence import create_evidence_bundle, verify_evidence_bundle
from dpo4000_utils.read_only_guard import ReadOnlyVisaSession
from dpo4000_utils.read_only_waveform import (
    ReadOnlyWaveformUnavailable,
    read_preconfigured_waveform,
)
from dpo4000_utils.recipe import Recipe, RecipeRunState, RecipeSequencer, RecipeStep
from dpo4000_utils.rules import (
    CompareOperator, RuleEngine, RuleSet, RuleStatus, ScalarRule,
    recipe_result_values,
)
from dpo4000_utils.scientific_export import (
    ScientificFormat, export_scientific_dataset, import_scientific_dataset,
)
from dpo4000_utils.settings import build_scope_settings_payload


@pytest.fixture(scope="module")
def readonly_scope():
    if os.getenv("DPO4000_HARDWARE") != "1":
        pytest.skip("Physical HIL disabled")
    if os.getenv("DPO4000_READONLY_AUTHORIZED") != "1":
        pytest.skip("Strict read-only bench authorization absent")
    resource = os.getenv("DPO4000_RESOURCE", "").strip()
    serial = os.getenv("DPO4000_EXPECT_SERIAL", "").strip()
    if not resource or not serial:
        pytest.fail("Operator resource and exact serial are mandatory")

    scope = DPO4054(
        resource, auto_connect=False,
        timeout_ms=int(os.getenv("DPO4000_TIMEOUT_MS", "20000")),
    )
    scope.connect()
    raw = scope.ensure_connected()
    locked = False
    baseline = None
    try:
        raw.lock_excl(timeout=scope.timeout_ms)
        locked = True
        scope.scope = ReadOnlyVisaSession(raw)
        fields = [field.strip() for field in scope.query_identity().split(",")]
        if len(fields) < 4 or not fields[0].upper().startswith("TEK") or fields[1].upper() != "DPO4054" or fields[2] != serial:
            pytest.fail(f"Unexpected physical instrument identity: {fields!r}")
        baseline = build_scope_settings_payload(scope.ensure_connected())
        yield scope
        after = build_scope_settings_payload(scope.ensure_connected())
        assert after["instrument"] == baseline["instrument"]
        assert after["setup"] == baseline["setup"], "Instrument configuration changed"
        assert scope.scope.blocked_count == 0, "Unsafe VISA operations were attempted"
    finally:
        try:
            if locked:
                raw.unlock()
        finally:
            scope.disconnect()


def _waveform(scope):
    if os.getenv("DPO4000_PROBE_COMP_CONFIRMED") != "1":
        pytest.skip("CH1 Probe Comp physical connection has not been confirmed")
    points = int(os.getenv("DPO4000_WAVEFORM_POINTS", "1000"))
    try:
        waveform = read_preconfigured_waveform(scope.ensure_connected(), max_points=points)
    except ReadOnlyWaveformUnavailable as exc:
        pytest.skip(str(exc))
    if waveform.source != "CH1":
        pytest.skip(f"Preconfigured DATA:SOURCE={waveform.source}; CH1 required")
    return waveform


def _out(tmp_path: Path) -> Path:
    root = Path(os.getenv("DPO4000_EVIDENCE_DIR", str(tmp_path)))
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.mark.hardware
def test_queryonly_waveform_samples_and_scaling(readonly_scope, tmp_path):
    w = _waveform(readonly_scope)
    assert w.sample_count > 0
    assert math.isfinite(w.time_at(0))
    assert math.isfinite(w.voltage_at(0))
    path = _out(tmp_path) / "preconfigured_waveform_summary.json"
    path.write_text(json.dumps({
        "source": w.source, "points": w.sample_count,
        "encoding": w.requested_encoding, "byte_width": w.preamble.byte_width,
        "first_time_s": w.time_at(0), "last_time_s": w.time_at(w.sample_count - 1),
        "first_voltage_v": w.voltage_at(0),
        "last_voltage_v": w.voltage_at(w.sample_count - 1),
        "transfer_start": w.start_index, "transfer_stop": w.stop_index,
    }, indent=2), encoding="utf-8")


@pytest.mark.hardware
def test_a18_real_preconfigured_waveform_evidence(readonly_scope, tmp_path):
    w = _waveform(readonly_scope)
    result = RecipeSequencer(readonly_scope).run(
        Recipe("A18 query-only", (RecipeStep.call("get_trigger_holdoff", name="HOLDOFF"),))
    )
    assert result.state is RecipeRunState.COMPLETED
    rules = RuleSet(
        "holdoff", ScalarRule("nonnegative", "HOLDOFF", CompareOperator.GTE, value=0.0),
    )
    verdict = RuleEngine().evaluate(rules, recipe_result_values(result))
    assert verdict.status is RuleStatus.PASS
    bundle = create_evidence_bundle(
        _out(tmp_path) / "a18_readonly_real_waveform.dpoe",
        recipe_result=result, rule_result=verdict,
        waveforms={w.source: w}, scope_identity=readonly_scope.query_identity(),
    )
    checked = verify_evidence_bundle(bundle.path)
    assert checked.bundle_sha256 == bundle.sha256


@pytest.mark.hardware
def test_a21_real_preconfigured_npz_dpoz_roundtrip(readonly_scope, tmp_path):
    w = _waveform(readonly_scope)
    root = _out(tmp_path)
    for fmt in (ScientificFormat.NPZ, ScientificFormat.DPOZ):
        dest = root / f"a21_readonly_real_waveform.{fmt.value}"
        written = export_scientific_dataset(
            dest, [w], format=fmt, metadata={"scope_identity": readonly_scope.query_identity()},
        )
        restored = import_scientific_dataset(dest)
        other = restored.dataset.waveforms[0]
        assert written.sample_count == w.sample_count
        assert other.samples.tolist() == w.samples.tolist()
        assert other.preamble == w.preamble


@pytest.mark.hardware
def test_a16_status_semantics_from_actual_readback(readonly_scope, tmp_path):
    """Demonstrate PASS/FAIL using one real number and INVALID via missing data."""
    actual = float(readonly_scope.get_trigger_holdoff())
    assert math.isfinite(actual)
    engine = RuleEngine()
    evaluations = {}
    for name, operator, boundary, expected in (
        ("pass", CompareOperator.GTE, actual, RuleStatus.PASS),
        ("fail", CompareOperator.LT, actual, RuleStatus.FAIL),
    ):
        rule = RuleSet(name, ScalarRule(name, "HOLDOFF", operator, value=boundary))
        verdict = engine.evaluate(rule, {"HOLDOFF": actual})
        assert verdict.status is expected
        evaluations[name] = verdict.status.value
    invalid = engine.evaluate(
        RuleSet("invalid", ScalarRule("missing", "HOLDOFF", CompareOperator.GTE, value=0.0)),
        {},
    )
    assert invalid.status is RuleStatus.INVALID
    evaluations["invalid_missing_input"] = invalid.status.value
    (_out(tmp_path) / "a16_real_value_status_matrix.json").write_text(
        json.dumps({"measured_holdoff_s": actual, "status": evaluations}, indent=2),
        encoding="utf-8",
    )
