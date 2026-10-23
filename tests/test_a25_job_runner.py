from __future__ import annotations

from array import array
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time

import pytest

from dpo4000_utils.job_runner import (
    HeadlessJobRunner,
    JobConfig,
    JobExitCode,
    JobValidationError,
    job_result_to_mapping,
    load_json_mapping,
    main,
    write_job_report,
)
from dpo4000_utils.scientific_export import import_scientific_dataset
from dpo4000_utils.waveform import WaveformData, WaveformPreamble


class FakeScope:
    def __init__(self, *_args, **_kwargs) -> None:
        self.identity = "TEKTRONIX,DPO4054,FAKE,0"
        self.closed = False

    def query_identity(self) -> str:
        return self.identity

    def read_value(self, value: float = 5.0) -> float:
        return float(value)

    def fail_step(self) -> None:
        raise RuntimeError("synthetic step failure")

    def read_enabled_waveforms(self, **_kwargs):
        preamble = WaveformPreamble(
            byte_width=2,
            encoding="RIBINARY",
            binary_format="RI",
            byte_order="MSB",
            record_point_count=3,
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
        waveform = WaveformData(
            source="CH1",
            label="rail",
            start_index=1,
            stop_index=3,
            requested_encoding="RIBINARY",
            preamble=preamble,
            samples=array("h", [100, 200, 300]),
            acquired_at=datetime(2026, 9, 26, tzinfo=timezone.utc),
        )
        return {"CH1": waveform}


class SessionRecorder:
    def __init__(self, scope: FakeScope | None = None) -> None:
        self.scope = scope or FakeScope()
        self.open_count = 0
        self.close_count = 0
        self.resources: list[str] = []

    @contextmanager
    def factory(self, resource, **_kwargs):
        self.open_count += 1
        self.resources.append(str(resource))
        try:
            yield self.scope
        finally:
            self.close_count += 1
            self.scope.closed = True


def _write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def _recipe(path: Path, *, method: str = "read_value", value: float = 5.0) -> Path:
    return _write_json(
        path,
        {
            "version": 1,
            "name": "headless test",
            "steps": [
                {
                    "kind": "call",
                    "name": "VALUE",
                    "method": method,
                    "args": [value] if method == "read_value" else [],
                }
            ],
        },
    )


def _rules(path: Path, operator: str, value: float) -> Path:
    return _write_json(
        path,
        {
            "version": 1,
            "name": "acceptance",
            "root": {
                "type": "compare",
                "id": "limit",
                "input": "VALUE",
                "operator": operator,
                "value": value,
            },
        },
    )


def _runner(recorder: SessionRecorder) -> HeadlessJobRunner:
    return HeadlessJobRunner(
        session_factory=recorder.factory,
        validation_target_factory=FakeScope,
    )


def test_validate_only_preflights_without_opening_session(tmp_path: Path) -> None:
    recorder = SessionRecorder()
    config = JobConfig(
        recipe_path=_recipe(tmp_path / "recipe.json"),
        validate_only=True,
    )
    result = _runner(recorder).run(config)
    assert result.exit_code is JobExitCode.SUCCESS
    assert result.status == "validated"
    assert recorder.open_count == recorder.close_count == 0


def test_invalid_later_method_is_rejected_before_session_io(tmp_path: Path) -> None:
    recipe = _write_json(
        tmp_path / "recipe.json",
        {
            "version": 1,
            "name": "bad later step",
            "steps": [
                {"kind": "call", "name": "ok", "method": "read_value"},
                {"kind": "call", "name": "bad", "method": "missing_method"},
            ],
        },
    )
    recorder = SessionRecorder()
    result = _runner(recorder).run(
        JobConfig(recipe_path=recipe, resource="FAKE::INSTR")
    )
    assert result.exit_code is JobExitCode.VALIDATION_ERROR
    assert recorder.open_count == 0


def test_completed_recipe_returns_success_and_closes_session(tmp_path: Path) -> None:
    recorder = SessionRecorder()
    result = _runner(recorder).run(
        JobConfig(
            recipe_path=_recipe(tmp_path / "recipe.json", value=5.0),
            resource="FAKE::INSTR",
            expect_idn="DPO4054",
        )
    )
    assert result.exit_code is JobExitCode.SUCCESS
    assert result.status == "completed"
    assert result.recipe_result is not None
    assert result.recipe_result.steps[0].value == 5.0
    assert recorder.open_count == recorder.close_count == 1


@pytest.mark.parametrize(
    ("operator", "limit", "exit_code", "status"),
    [
        (">=", 4.9, JobExitCode.SUCCESS, "pass"),
        (">", 5.1, JobExitCode.RULE_FAILED, "fail"),
    ],
)
def test_rule_status_maps_to_stable_exit_codes(
    tmp_path: Path,
    operator: str,
    limit: float,
    exit_code: JobExitCode,
    status: str,
) -> None:
    recorder = SessionRecorder()
    result = _runner(recorder).run(
        JobConfig(
            recipe_path=_recipe(tmp_path / "recipe.json", value=5.0),
            rules_path=_rules(tmp_path / "rules.json", operator, limit),
            resource="FAKE::INSTR",
        )
    )
    assert result.exit_code is exit_code
    assert result.status == status
    assert result.rule_result is not None
    assert recorder.close_count == 1


def test_missing_rule_input_returns_invalid_exit_code(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path / "recipe.json")
    rules = _write_json(
        tmp_path / "rules.json",
        {
            "version": 1,
            "name": "missing",
            "root": {
                "type": "compare",
                "id": "missing",
                "input": "DOES_NOT_EXIST",
                "operator": ">=",
                "value": 0.0,
            },
        },
    )
    result = _runner(SessionRecorder()).run(
        JobConfig(recipe_path=recipe, rules_path=rules, resource="FAKE::INSTR")
    )
    assert result.exit_code is JobExitCode.RULE_INVALID
    assert result.status == "invalid"


def test_recipe_failure_has_distinct_exit_code(tmp_path: Path) -> None:
    recorder = SessionRecorder()
    result = _runner(recorder).run(
        JobConfig(
            recipe_path=_recipe(tmp_path / "recipe.json", method="fail_step"),
            resource="FAKE::INSTR",
        )
    )
    assert result.exit_code is JobExitCode.RECIPE_FAILED
    assert "synthetic step failure" in result.message
    assert recorder.close_count == 1


def test_identity_mismatch_is_runtime_error_and_still_closes(tmp_path: Path) -> None:
    recorder = SessionRecorder()
    result = _runner(recorder).run(
        JobConfig(
            recipe_path=_recipe(tmp_path / "recipe.json"),
            resource="FAKE::INSTR",
            expect_idn="NOT-THIS-SCOPE",
        )
    )
    assert result.exit_code is JobExitCode.RUNTIME_ERROR
    assert recorder.open_count == recorder.close_count == 1


def test_cancel_before_run_does_not_open_session(tmp_path: Path) -> None:
    recorder = SessionRecorder()
    runner = _runner(recorder)
    runner.cancel()
    result = runner.run(
        JobConfig(
            recipe_path=_recipe(tmp_path / "recipe.json"),
            resource="FAKE::INSTR",
        )
    )
    assert result.exit_code is JobExitCode.CANCELLED
    assert recorder.open_count == 0


def test_cancel_interrupts_delay_and_session_is_closed(tmp_path: Path) -> None:
    recipe = _write_json(
        tmp_path / "recipe.json",
        {
            "version": 1,
            "name": "cancel delay",
            "steps": [{"kind": "delay", "name": "wait", "seconds": 2.0}],
        },
    )
    recorder = SessionRecorder()
    runner = _runner(recorder)
    holder: list[object] = []

    thread = threading.Thread(
        target=lambda: holder.append(
            runner.run(JobConfig(recipe_path=recipe, resource="FAKE::INSTR"))
        )
    )
    started = time.perf_counter()
    thread.start()
    time.sleep(0.1)
    runner.cancel()
    thread.join(timeout=1.0)
    elapsed = time.perf_counter() - started
    assert not thread.is_alive()
    result = holder[0]
    assert result.exit_code is JobExitCode.CANCELLED
    assert elapsed < 1.0
    assert recorder.close_count == 1


def test_optional_dpoz_export_reuses_a21_and_round_trips(tmp_path: Path) -> None:
    recorder = SessionRecorder()
    export_path = tmp_path / "waveforms.dpoz"
    result = _runner(recorder).run(
        JobConfig(
            recipe_path=_recipe(tmp_path / "recipe.json"),
            resource="FAKE::INSTR",
            scientific_export_path=export_path,
            scientific_points=3,
        )
    )
    assert result.exit_code is JobExitCode.SUCCESS
    assert result.scientific_export is not None
    imported = import_scientific_dataset(export_path)
    waveform = imported.dataset.by_source()["CH1"]
    assert list(waveform.samples) == [100, 200, 300]
    assert imported.dataset.metadata["recipe"] == "headless test"


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"version": 1, "version": 1, "name": "x", "steps": []}', encoding="utf-8")
    with pytest.raises(JobValidationError, match="duplicate JSON key"):
        load_json_mapping(path, label="recipe")


def test_atomic_report_has_stable_schema(tmp_path: Path) -> None:
    result = _runner(SessionRecorder()).run(
        JobConfig(
            recipe_path=_recipe(tmp_path / "recipe.json"),
            resource="FAKE::INSTR",
        )
    )
    report = write_job_report(tmp_path / "result.json", result)
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["schema"] == "dpo4000-headless-job"
    assert payload["schema_version"] == 1
    assert payload["exit_code"] == 0
    assert payload["recipe_result"]["state"] == "completed"
    assert job_result_to_mapping(result)["status"] == "completed"


def test_cli_validate_only_uses_real_driver_signature_without_visa(
    tmp_path: Path,
    capsys,
) -> None:
    recipe = _write_json(
        tmp_path / "recipe.json",
        {
            "version": 1,
            "name": "validation smoke",
            "steps": [
                {"kind": "call", "name": "IDN", "method": "query_identity"}
            ],
        },
    )
    assert main(["--recipe", str(recipe), "--validate-only"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "validated"
    assert output["resource"] is None
