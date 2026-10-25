from __future__ import annotations

import json
from pathlib import Path

from dpo4000_utils.job_runner import JobConfig, JobExitCode, format_job_summary, main

from test_a25_job_runner import SessionRecorder, _recipe, _rules, _runner, _write_json


def test_summary_for_passing_job(tmp_path: Path) -> None:
    result = _runner(SessionRecorder()).run(
        JobConfig(
            recipe_path=_recipe(tmp_path / "recipe.json", value=5.0),
            rules_path=_rules(tmp_path / "rules.json", ">=", 4.5),
            resource="USB0::TEST::INSTR",
        )
    )
    assert result.exit_code is JobExitCode.SUCCESS
    lines = format_job_summary(result).splitlines()
    assert lines[0].startswith("dpo4000-job: PASS (exit 0) in ")
    assert "Recipe: headless test" in lines
    assert any(line.startswith("Scope: TEKTRONIX") for line in lines)
    assert any(line.startswith("Steps: completed, 1 steps") for line in lines)
    assert "Rules: acceptance PASS (1 PASS)" in lines
    assert not any(line.startswith("Message:") for line in lines)


def test_summary_lists_failing_rules_and_message(tmp_path: Path) -> None:
    result = _runner(SessionRecorder()).run(
        JobConfig(
            recipe_path=_recipe(tmp_path / "recipe.json", value=5.0),
            rules_path=_rules(tmp_path / "rules.json", "<", 1.0),
            resource="USB0::TEST::INSTR",
        )
    )
    assert result.exit_code is JobExitCode.RULE_FAILED
    summary = format_job_summary(result)
    assert summary.splitlines()[0].startswith("dpo4000-job: RULE FAILED (exit 5)")
    assert "  FAIL limit: actual 5 — condition not satisfied" in summary
    assert "Message: A16 rule set evaluated to FAIL" in summary


def test_cli_text_output_for_validation_and_errors(tmp_path: Path, capsys) -> None:
    recipe = _write_json(
        tmp_path / "recipe.json",
        {"version": 1, "name": "text smoke", "steps": [{"kind": "call", "name": "IDN", "method": "query_identity"}]},
    )
    assert main(["--recipe", str(recipe), "--validate-only", "--output-format", "text"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("dpo4000-job: VALIDATED (exit 0)")
    assert "Recipe: text smoke (validation only)" in out

    assert main(["--recipe", str(tmp_path / "missing.json"), "--output-format", "text"]) == 2
    out = capsys.readouterr().out
    assert out.startswith("dpo4000-job: VALIDATION ERROR (exit 2)")
    assert "Message: " in out


def test_json_remains_default_and_report_is_unaffected(tmp_path: Path, capsys) -> None:
    recipe = _write_json(
        tmp_path / "recipe.json",
        {"version": 1, "name": "json default", "steps": [{"kind": "call", "name": "IDN", "method": "query_identity"}]},
    )
    report = tmp_path / "report.json"
    assert main(["--recipe", str(recipe), "--validate-only", "--report", str(report), "--output-format", "text"]) == 0
    capsys.readouterr()
    assert json.loads(report.read_text())["status"] == "validated"
    assert main(["--recipe", str(recipe), "--validate-only"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "validated"
