from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path

import pytest

from dpo4000_utils.job_runner import (
    HeadlessJobRunner,
    JobConfig,
    JobExitCode,
    JobValidationError,
)
from dpo4000_utils.scientific_export import ScientificExportError


class ExportFailureScope:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def query_identity(self) -> str:
        return "TEKTRONIX,DPO4054,FAKE,0"

    def read_value(self) -> float:
        return 1.0

    def read_enabled_waveforms(self, **_kwargs):
        raise ScientificExportError("synthetic export acquisition failure")


@contextmanager
def _session(_resource, **_kwargs):
    yield ExportFailureScope()


def _recipe(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "name": "export error",
                "steps": [
                    {"kind": "call", "name": "VALUE", "method": "read_value"}
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_requested_export_failure_has_distinct_exit_code(tmp_path: Path) -> None:
    runner = HeadlessJobRunner(
        session_factory=_session,
        validation_target_factory=ExportFailureScope,
    )
    result = runner.run(
        JobConfig(
            recipe_path=_recipe(tmp_path / "recipe.json"),
            resource="FAKE::INSTR",
            scientific_export_path=tmp_path / "capture.dpoz",
        )
    )
    assert result.exit_code is JobExitCode.EXPORT_ERROR
    assert result.status == "export_error"
    assert "synthetic export" in result.message


def test_execution_requires_resource(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path / "recipe.json")
    with pytest.raises(JobValidationError, match="resource is required"):
        JobConfig(recipe_path=recipe)


def test_export_options_require_export_path(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path / "recipe.json")
    with pytest.raises(JobValidationError, match="require scientific_export_path"):
        JobConfig(
            recipe_path=recipe,
            resource="FAKE::INSTR",
            scientific_points=1000,
        )


def test_validate_only_rejects_export_request(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path / "recipe.json")
    with pytest.raises(JobValidationError, match="not available in validate-only"):
        JobConfig(
            recipe_path=recipe,
            validate_only=True,
            scientific_export_path=tmp_path / "capture.dpoz",
        )
