from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from dpo4000_utils.evidence import verify_evidence_bundle
from dpo4000_utils.job_runner import (
    JobConfig,
    JobExitCode,
    JobValidationError,
    job_result_to_mapping,
    main,
)

from test_a25_job_runner import FakeScope, SessionRecorder, _recipe, _rules, _runner, _write_json


class SetupScope(FakeScope):
    """Fake scope that answers the read-only *LRN? setup query and records reads."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setup_reads = 0

    def query(self, command: str) -> str:
        assert command == "*LRN?", command
        self.setup_reads += 1
        return f":SETUP {self.setup_reads}"


def _run(tmp_path: Path, *, operator: str = ">=", method: str = "read_value", scope=None):
    recorder = SessionRecorder(scope or SetupScope())
    config = JobConfig(
        recipe_path=_recipe(tmp_path / "recipe.json", method=method),
        rules_path=_rules(tmp_path / "rules.json", operator, 4.5),
        resource="TCPIP0::192.0.2.9::inst0::INSTR",
        evidence_path=tmp_path / "out" / "run",
    )
    return config, recorder, _runner(recorder).run(config)


def test_evidence_bundle_for_passing_job(tmp_path: Path) -> None:
    config, recorder, result = _run(tmp_path)
    assert result.exit_code is JobExitCode.SUCCESS
    assert config.evidence_path == tmp_path / "out" / "run.dpoe"
    assert result.evidence is not None and result.evidence.path == config.evidence_path
    manifest = verify_evidence_bundle(config.evidence_path).manifest
    assert manifest["transport"] == "TCPIP"
    assert manifest["rule_status"] == "PASS"
    with ZipFile(config.evidence_path) as archive:
        names = set(archive.namelist())
        assert {"definitions/recipe.json", "definitions/rules.json", "report/summary.md"} <= names
        assert archive.read("setup/before.txt") == b":SETUP 1"
        assert archive.read("setup/after.txt") == b":SETUP 2"
        for name in names:
            assert b"192.0.2.9" not in archive.read(name)
    report = job_result_to_mapping(result)["evidence"]
    assert report["path"] == str(config.evidence_path)
    assert report["sha256"] == result.evidence.sha256
    assert recorder.close_count == 1


def test_evidence_is_written_for_rule_failure(tmp_path: Path) -> None:
    config, _recorder, result = _run(tmp_path, operator="<")
    assert result.exit_code is JobExitCode.RULE_FAILED
    assert verify_evidence_bundle(config.evidence_path).manifest["rule_status"] == "FAIL"


def test_evidence_is_written_for_failed_recipe_and_failure_stays_the_outcome(tmp_path: Path) -> None:
    config, _recorder, result = _run(tmp_path, method="fail_step")
    assert result.exit_code is JobExitCode.RECIPE_FAILED
    assert result.evidence is not None
    assert verify_evidence_bundle(config.evidence_path).manifest["recipe_state"] == "failed"


def test_evidence_failure_is_export_error_for_completed_runs(tmp_path: Path, monkeypatch) -> None:
    import dpo4000_utils.job_runner as job_runner

    def broken(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(job_runner, "create_evidence_bundle", broken)
    _config, recorder, result = _run(tmp_path)
    assert result.exit_code is JobExitCode.EXPORT_ERROR
    assert result.message == "evidence: disk full"
    assert result.evidence is None
    assert recorder.close_count == 1


def test_evidence_failure_does_not_mask_recipe_failure(tmp_path: Path, monkeypatch) -> None:
    import dpo4000_utils.job_runner as job_runner

    def broken(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(job_runner, "create_evidence_bundle", broken)
    _config, _recorder, result = _run(tmp_path, method="fail_step")
    assert result.exit_code is JobExitCode.RECIPE_FAILED
    assert "evidence not written: disk full" in result.message


def test_no_setup_reads_without_evidence(tmp_path: Path) -> None:
    scope = SetupScope()
    recorder = SessionRecorder(scope)
    result = _runner(recorder).run(
        JobConfig(recipe_path=_recipe(tmp_path / "recipe.json"), resource="USB0::TEST::INSTR")
    )
    assert result.exit_code is JobExitCode.SUCCESS
    assert scope.setup_reads == 0
    assert job_result_to_mapping(result)["evidence"] is None


def test_evidence_path_validation(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path / "recipe.json")
    with pytest.raises(JobValidationError, match="validate-only"):
        JobConfig(recipe_path=recipe, validate_only=True, evidence_path=tmp_path / "e.dpoe")
    with pytest.raises(JobValidationError, match="distinct"):
        JobConfig(
            recipe_path=recipe,
            resource="USB0::TEST::INSTR",
            report_path=tmp_path / "same.dpoe",
            evidence_path=tmp_path / "same",
        )
    # A .json evidence path is normalized to .dpoe, so it cannot replace the recipe...
    assert JobConfig(recipe_path=recipe, resource="USB0::TEST::INSTR", evidence_path=recipe).evidence_path == (
        tmp_path / "recipe.dpoe"
    )
    # ...but an input that already ends in .dpoe is still protected.
    odd_rules = _rules(tmp_path / "rules.dpoe", ">", 0.0)
    with pytest.raises(JobValidationError, match="must not replace"):
        JobConfig(
            recipe_path=recipe,
            rules_path=odd_rules,
            resource="USB0::TEST::INSTR",
            evidence_path=tmp_path / "rules",
        )


def test_cli_rejects_evidence_with_validate_only(tmp_path: Path, capsys) -> None:
    recipe = _write_json(
        tmp_path / "recipe.json",
        {"version": 1, "name": "x", "steps": [{"kind": "call", "name": "IDN", "method": "query_identity"}]},
    )
    code = main(["--recipe", str(recipe), "--validate-only", "--evidence", str(tmp_path / "e.dpoe")])
    assert code == int(JobExitCode.VALIDATION_ERROR)
    assert "validate-only" in json.loads(capsys.readouterr().out)["message"]
