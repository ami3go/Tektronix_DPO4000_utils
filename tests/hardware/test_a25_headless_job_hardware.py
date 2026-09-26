"""Read-only A25 headless runner qualification against a real DPO4054."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from dpo4000_utils.job_runner import (
    HeadlessJobRunner,
    JobConfig,
    JobExitCode,
    write_job_report,
)

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


@pytest.mark.hardware
def test_a25_read_only_recipe_rule_and_report(tmp_path: Path) -> None:
    if not _env_enabled("DPO4000_HARDWARE"):
        pytest.skip("Set DPO4000_HARDWARE=1 to run A25 hardware qualification.")
    resource = os.getenv("DPO4000_RESOURCE", "").strip()
    if not resource:
        pytest.skip("Set DPO4000_RESOURCE to the oscilloscope VISA resource.")

    recipe_path = tmp_path / "a25-recipe.json"
    rules_path = tmp_path / "a25-rules.json"
    report_path = tmp_path / "a25-report.json"
    recipe_path.write_text(
        json.dumps(
            {
                "version": 1,
                "name": "A25 read-only holdoff",
                "steps": [
                    {
                        "kind": "call",
                        "name": "HOLDOFF",
                        "method": "get_trigger_holdoff",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    rules_path.write_text(
        json.dumps(
            {
                "version": 1,
                "name": "holdoff sanity",
                "root": {
                    "type": "compare",
                    "id": "holdoff_non_negative",
                    "input": "HOLDOFF",
                    "operator": ">=",
                    "value": 0.0,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = HeadlessJobRunner().run(
        JobConfig(
            recipe_path=recipe_path,
            rules_path=rules_path,
            resource=resource,
            timeout_ms=int(os.getenv("DPO4000_TIMEOUT_MS", "20000")),
            expect_idn=os.getenv("DPO4000_EXPECT_IDN", "TEKTRONIX,DPO4054"),
        )
    )
    assert result.exit_code is JobExitCode.SUCCESS
    assert result.status == "pass"
    assert result.recipe_result is not None
    assert result.rule_result is not None
    assert float(result.recipe_result.steps[0].value) >= 0.0

    write_job_report(report_path, result)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["schema"] == "dpo4000-headless-job"
    assert payload["exit_code"] == 0
    assert payload["status"] == "pass"
