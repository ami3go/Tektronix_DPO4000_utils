"""A18 evidence bundle qualification against a real DPO4054."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from dpo4000_utils import DPO4054
from dpo4000_utils.connection import visaResourceAddr
from dpo4000_utils.evidence import create_evidence_bundle, verify_evidence_bundle
from dpo4000_utils.recipe import Recipe, RecipeRunState, RecipeSequencer, RecipeStep
from dpo4000_utils.rules import (
    CompareOperator,
    RuleEngine,
    RuleSet,
    RuleStatus,
    ScalarRule,
    recipe_result_values,
)

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


@pytest.fixture(scope="module")
def a18_scope():
    if not _env_enabled("DPO4000_HARDWARE"):
        pytest.skip("Set DPO4000_HARDWARE=1 to run A18 hardware qualification.")
    resource = os.getenv("DPO4000_RESOURCE", visaResourceAddr).strip()
    if not resource:
        pytest.skip("Set DPO4000_RESOURCE to the oscilloscope VISA resource.")
    scope = DPO4054(
        resource,
        auto_connect=False,
        timeout_ms=int(os.getenv("DPO4000_TIMEOUT_MS", "20000")),
    )
    scope.connect()
    try:
        identity = scope.query_identity()
        expected = os.getenv("DPO4000_EXPECT_IDN", "TEKTRONIX,DPO4054").strip()
        assert expected.upper() in identity.upper()
        yield scope
    finally:
        scope.disconnect()


@pytest.mark.hardware
def test_a18_read_only_waveform_bundle_round_trip(a18_scope, tmp_path: Path) -> None:
    recipe = Recipe(
        "A18 holdoff evidence",
        (RecipeStep.call("get_trigger_holdoff", name="HOLDOFF"),),
    )
    recipe_result = RecipeSequencer(a18_scope).run(recipe)
    assert recipe_result.state is RecipeRunState.COMPLETED
    rules = RuleSet(
        "Holdoff sanity",
        ScalarRule("holdoff_non_negative", "HOLDOFF", CompareOperator.GTE, value=0.0),
    )
    rule_result = RuleEngine().evaluate(rules, recipe_result_values(recipe_result))
    assert rule_result.status is RuleStatus.PASS

    waveform = a18_scope.read_channel_waveform_data(1, point_count=1000)
    bundle = create_evidence_bundle(
        tmp_path / "a18-read-only.dpoe",
        recipe_result=recipe_result,
        rule_result=rule_result,
        waveforms={waveform.source: waveform},
        scope_identity=a18_scope.query_identity(),
        metadata={"qualification": "DPO4054", "screen": False},
    )
    verified = verify_evidence_bundle(bundle.path)
    assert verified.bundle_sha256 == bundle.sha256
    assert verified.manifest["rule_status"] == "PASS"
    assert any(
        item["path"] == f"waveforms/{waveform.source}.raw"
        for item in verified.manifest["artifacts"]
    )


@pytest.mark.hardware
def test_a18_reversible_real_screen_bundle(a18_scope, tmp_path: Path) -> None:
    if not _env_enabled("DPO4000_ENABLE_WRITE_TESTS"):
        pytest.skip("Set DPO4000_ENABLE_WRITE_TESTS=1 for reversible hardcopy qualification.")
    recipe_result = RecipeSequencer(a18_scope).run(
        Recipe("A18 screen evidence", (RecipeStep.call("get_trigger_holdoff", name="HOLDOFF"),))
    )
    screen = a18_scope.read_screen_png()
    assert screen.startswith(b"\x89PNG\r\n\x1a\n")
    bundle = create_evidence_bundle(
        tmp_path / "a18-screen.dpoe",
        recipe_result=recipe_result,
        screen_png=screen,
        scope_identity=a18_scope.query_identity(),
        metadata={"qualification": "DPO4054", "screen": True},
    )
    verified = verify_evidence_bundle(bundle.path)
    assert any(item["path"] == "screen/scope.png" for item in verified.manifest["artifacts"])
