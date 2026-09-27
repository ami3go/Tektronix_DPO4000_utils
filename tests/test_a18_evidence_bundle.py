from __future__ import annotations

from array import array
from datetime import datetime, timezone
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from dpo4000_utils.evidence import (
    EvidenceBundleCancelled,
    EvidenceBundleError,
    create_evidence_bundle,
    verify_evidence_bundle,
)
from dpo4000_utils.recipe import RecipeResult, RecipeRunState, StepResult
from dpo4000_utils.rules import (
    CompareOperator,
    RuleEngine,
    RuleSet,
    RuleStatus,
    ScalarRule,
)
from dpo4000_utils.waveform import WaveformData, WaveformPreamble

_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0bIDAT\x08\xd7c\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb1"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
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


def _rule_result():
    rule = RuleSet(
        "5 V",
        ScalarRule("vmin", "MEAS1", CompareOperator.GTE, value=4.95),
    )
    return RuleEngine().evaluate(rule, {"MEAS1": 5.01}, timestamp="2026-09-27T00:00:00+00:00")


def _waveform(source: str = "CH1", count: int = 8) -> WaveformData:
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
    return WaveformData(
        source=source,
        label="probe",
        start_index=1,
        stop_index=count,
        requested_encoding="RIBINARY",
        preamble=preamble,
        samples=array("h", range(count)),
        acquired_at=datetime(2026, 9, 27, tzinfo=timezone.utc),
    )


def test_create_and_verify_complete_bundle(tmp_path: Path) -> None:
    path = tmp_path / "result.dpoe"
    result = create_evidence_bundle(
        path,
        recipe_result=_recipe_result(),
        rule_result=_rule_result(),
        screen_png=_PNG,
        waveforms={"CH1": _waveform()},
        scope_identity="TEKTRONIX,DPO4054,SERIAL,2.68",
        metadata={"fixture": "probe-comp", "run": 7},
    )
    assert result.path == path
    assert result.size_bytes == path.stat().st_size
    assert result.artifact_count == 5
    assert len(result.sha256) == 64
    assert result.metrics.total_s >= result.metrics.finalize_s >= 0

    verified = verify_evidence_bundle(path)
    assert verified.artifact_count == result.artifact_count
    assert verified.bundle_sha256 == result.sha256
    assert verified.manifest["recipe_name"] == "A18 example"
    assert verified.manifest["rule_status"] == RuleStatus.PASS.value
    assert verified.manifest["scope_identity"].startswith("TEKTRONIX,DPO4054")

    with ZipFile(path, "r") as archive:
        index = json.loads(archive.read("waveforms/index.json"))
        item = index["waveforms"][0]
        assert item["source"] == "CH1"
        assert item["sample_count"] == 8
        assert item["preamble"]["x_increment"] == 1e-6
        assert archive.read("waveforms/CH1.raw") == _waveform().samples.tobytes()
        recipe = json.loads(archive.read("results/recipe_result.json"))
        assert recipe["steps"][1]["value"]["type"] == "bytes"
        assert recipe["steps"][1]["value"]["size"] == len(b"binary result")


def test_suffix_is_added_and_minimal_bundle_is_valid(tmp_path: Path) -> None:
    result = create_evidence_bundle(tmp_path / "minimal", recipe_result=_recipe_result())
    assert result.path.suffix == ".dpoe"
    verified = verify_evidence_bundle(result.path)
    assert verified.artifact_count == 1
    assert verified.manifest["rule_status"] is None


def test_existing_destination_survives_cancel(tmp_path: Path) -> None:
    destination = tmp_path / "existing.dpoe"
    destination.write_bytes(b"ORIGINAL")
    calls = 0

    def cancel() -> bool:
        nonlocal calls
        calls += 1
        return calls >= 2

    with pytest.raises(EvidenceBundleCancelled):
        create_evidence_bundle(
            destination,
            recipe_result=_recipe_result(),
            screen_png=_PNG,
            waveforms={"CH1": _waveform(count=100)},
            cancel=cancel,
        )
    assert destination.read_bytes() == b"ORIGINAL"
    assert not list(tmp_path.glob(".*.tmp"))


def test_invalid_png_is_rejected_before_destination_change(tmp_path: Path) -> None:
    destination = tmp_path / "existing.dpoe"
    destination.write_bytes(b"ORIGINAL")
    with pytest.raises(EvidenceBundleError, match="PNG"):
        create_evidence_bundle(
            destination,
            recipe_result=_recipe_result(),
            screen_png=b"not-png",
        )
    assert destination.read_bytes() == b"ORIGINAL"


def test_hash_corruption_is_detected(tmp_path: Path) -> None:
    good = tmp_path / "good.dpoe"
    bad = tmp_path / "bad.dpoe"
    create_evidence_bundle(good, recipe_result=_recipe_result(), screen_png=_PNG)
    with ZipFile(good, "r") as source, ZipFile(bad, "w", compression=ZIP_DEFLATED) as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "screen/scope.png":
                data = data[:-1] + bytes([data[-1] ^ 0x01])
            target.writestr(info.filename, data)
    with pytest.raises(EvidenceBundleError, match="hash mismatch"):
        verify_evidence_bundle(bad)
