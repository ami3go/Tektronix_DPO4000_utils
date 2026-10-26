from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from dpo4000_utils.evidence import (
    EVIDENCE_VERSION,
    SUPPORTED_EVIDENCE_VERSIONS,
    EvidenceBundleError,
    _transport_from_resource,
    create_evidence_bundle,
    verify_evidence_bundle,
)
from dpo4000_utils.recipe import (
    Recipe,
    RecipeResult,
    RecipeRunState,
    RecipeStep,
    StepResult,
    recipe_to_mapping,
)
from dpo4000_utils.rules import (
    CompareOperator,
    RuleEngine,
    RuleSet,
    ScalarRule,
    rule_set_to_mapping,
)


def _recipe_result() -> RecipeResult:
    return RecipeResult(
        "A18 example",
        RecipeRunState.COMPLETED,
        1.0,
        1.25,
        (
            StepResult(0, "MEAS1", 1, 1.0, 1.1, 5.01),
            StepResult(1, "blob", 1, 1.1, 1.2, b"binary result"),
        ),
    )


def _rule_set() -> RuleSet:
    return RuleSet("5 V", ScalarRule("vmin", "MEAS1", CompareOperator.GTE, value=4.95))


def _rule_result():
    return RuleEngine().evaluate(_rule_set(), {"MEAS1": 5.01}, timestamp="2026-09-27T00:00:00+00:00")


def _recipe() -> Recipe:
    return Recipe(
        "A18 example",
        (RecipeStep.call("get_measurement_value", 1, name="MEAS1"), RecipeStep.delay(0.0)),
    )


def _rewrite_manifest(source: Path, target: Path, **changes) -> Path:
    """Copy a bundle, replacing manifest keys; a value of ``...`` deletes the key."""
    with ZipFile(source) as archive, ZipFile(target, "w") as rewritten:
        manifest = json.loads(archive.read("manifest.json"))
        for key, value in changes.items():
            if value is ...:
                del manifest[key]
            else:
                manifest[key] = value
        for name in archive.namelist():
            data = archive.read(name)
            if name == "manifest.json":
                data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
            rewritten.writestr(name, data)
    return target


def test_v2_bundle_records_definitions_setup_and_summary(tmp_path: Path) -> None:
    path = tmp_path / "result.dpoe"
    create_evidence_bundle(
        path,
        recipe_result=_recipe_result(),
        rule_result=_rule_result(),
        recipe=_recipe(),
        rule_set=_rule_set(),
        resource="USB0::0x0699::0x0401::C000000::INSTR",
        setup_before="BEFORE;",
        setup_after="AFTER;",
    )

    manifest = verify_evidence_bundle(path).manifest
    assert manifest["version"] == EVIDENCE_VERSION == 2
    assert SUPPORTED_EVIDENCE_VERSIONS == (1, 2)
    assert manifest["transport"] == "USB"
    kinds = {artifact["kind"] for artifact in manifest["artifacts"]}
    assert {
        "recipe_definition",
        "rule_definition",
        "scope_setup_before",
        "scope_setup_after",
        "summary_report",
    } <= kinds

    with ZipFile(path) as archive:
        assert json.loads(archive.read("definitions/recipe.json")) == recipe_to_mapping(_recipe())
        assert json.loads(archive.read("definitions/rules.json")) == rule_set_to_mapping(_rule_set())
        assert archive.read("setup/before.txt") == b"BEFORE;"
        assert archive.read("setup/after.txt") == b"AFTER;"
        summary = archive.read("report/summary.md").decode("utf-8")
    assert "# Evidence: A18 example" in summary
    assert f"**{RecipeRunState.COMPLETED.value}**" in summary
    assert "**PASS** `vmin`" in summary
    assert "Transport: USB" in summary


def test_full_resource_string_is_not_stored(tmp_path: Path) -> None:
    path = tmp_path / "result.dpoe"
    create_evidence_bundle(
        path,
        recipe_result=_recipe_result(),
        resource="TCPIP0::10.1.2.3::inst0::INSTR",
    )
    with ZipFile(path) as archive:
        for name in archive.namelist():
            assert b"10.1.2.3" not in archive.read(name), name
    assert verify_evidence_bundle(path).manifest["transport"] == "TCPIP"


@pytest.mark.parametrize(
    ("resource", "expected"),
    [
        ("USB0::0x0699::0x0401::X::INSTR", "USB"),
        ("TCPIP0::host::inst0::INSTR", "TCPIP"),
        ("TCPIP0::host::4000::SOCKET", "TCPIP-SOCKET"),
        ("GPIB0::1::INSTR", "GPIB"),
        ("ASRL1::INSTR", "SERIAL"),
        ("weird", "OTHER"),
        ("", None),
        (None, None),
    ],
)
def test_transport_classification(resource, expected) -> None:
    assert _transport_from_resource(resource) == expected


def test_environment_metadata_uses_build_commit_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DPO4000_BUILD_COMMIT", "abc123")
    path = tmp_path / "result.dpoe"
    create_evidence_bundle(path, recipe_result=_recipe_result())
    environment = verify_evidence_bundle(path).manifest["environment"]
    assert environment["build_commit"] == "abc123"
    assert environment["python_version"]


def test_summary_can_be_disabled(tmp_path: Path) -> None:
    path = tmp_path / "result.dpoe"
    create_evidence_bundle(path, recipe_result=_recipe_result(), include_summary=False)
    assert verify_evidence_bundle(path).artifact_count == 1
    with ZipFile(path) as archive:
        assert "report/summary.md" not in archive.namelist()


@pytest.mark.parametrize("field", ["setup_before", "setup_after"])
def test_setup_must_be_text_and_nothing_is_written(tmp_path: Path, field: str) -> None:
    path = tmp_path / "result.dpoe"
    with pytest.raises(EvidenceBundleError, match=field):
        create_evidence_bundle(path, recipe_result=_recipe_result(), **{field: b"bytes"})
    assert list(tmp_path.iterdir()) == []


def test_v1_manifest_still_verifies(tmp_path: Path) -> None:
    source = tmp_path / "v2.dpoe"
    create_evidence_bundle(source, recipe_result=_recipe_result(), include_summary=False)
    v1 = _rewrite_manifest(source, tmp_path / "v1.dpoe", version=1, transport=..., environment=...)
    assert verify_evidence_bundle(v1).manifest["version"] == 1


@pytest.mark.parametrize("field", ["transport", "environment"])
def test_v1_manifest_rejects_v2_only_fields(tmp_path: Path, field: str) -> None:
    source = tmp_path / "v2.dpoe"
    create_evidence_bundle(source, recipe_result=_recipe_result(), include_summary=False)
    other = "environment" if field == "transport" else "transport"
    bad = _rewrite_manifest(source, tmp_path / "bad.dpoe", version=1, **{other: ...})
    with pytest.raises(EvidenceBundleError, match="Unknown evidence manifest fields"):
        verify_evidence_bundle(bad)


@pytest.mark.parametrize("version", [0, 3, True, "2", None])
def test_unsupported_version_rejected(tmp_path: Path, version) -> None:
    source = tmp_path / "v2.dpoe"
    create_evidence_bundle(source, recipe_result=_recipe_result(), include_summary=False)
    bad = _rewrite_manifest(source, tmp_path / "bad.dpoe", version=version)
    with pytest.raises(EvidenceBundleError):
        verify_evidence_bundle(bad)
