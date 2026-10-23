"""A25 security, cancellation, concurrency, CLI and atomicity regression gates."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from dpo4000_utils.job_runner import (
    HeadlessJobRunner,
    JobConfig,
    JobExitCode,
    JobValidationError,
    load_json_mapping,
    main,
    write_job_report,
)


class Scope:
    def __init__(self, *_args, **_kwargs) -> None:
        self.calls = 0
        self.started = threading.Event()
        self.release = threading.Event()

    def query_identity(self) -> str:
        return "TEKTRONIX,DPO4054,FAKE,0"

    def measure(self) -> float:
        self.calls += 1
        return 5.0

    def wait_for_release(self) -> float:
        self.calls += 1
        self.started.set()
        if not self.release.wait(timeout=4):
            raise RuntimeError("test worker timed out")
        return 5.0


class Recorder:
    def __init__(self) -> None:
        self.scope = Scope()
        self.opened = 0
        self.closed = 0

    @contextmanager
    def session(self, _resource, **_kwargs):
        self.opened += 1
        try:
            yield self.scope
        finally:
            self.closed += 1

    def runner(self) -> HeadlessJobRunner:
        return HeadlessJobRunner(
            session_factory=self.session, validation_target_factory=Scope
        )


def _recipe(tmp_path: Path, methods: tuple[str, ...] = ("measure",)) -> Path:
    path = tmp_path / "recipe.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "name": "a25 safety",
                "steps": [
                    {"kind": "call", "name": f"STEP{i}", "method": method}
                    for i, method in enumerate(methods)
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    "document",
    [
        b'{"name": NaN}',
        b'{"name": Infinity}',
        b'{"name": -Infinity}',
        b'{"name": 1, "name": 2}',
        b'not json',
        b'[]',
        b'\xff\xfe\xfd',
    ],
)
def test_strict_json_rejects_malformed_content(tmp_path: Path, document: bytes) -> None:
    path = tmp_path / "invalid.json"
    path.write_bytes(document)
    with pytest.raises(JobValidationError):
        load_json_mapping(path, label="recipe")


@pytest.mark.parametrize(
    "document",
    [
        b'{"x": 1e999}',
        b'{"x": ' + b'9' * 129 + b'}',
        b'{"nested":' + b'[' * 4000 + b'0' + b']' * 4000 + b'}',
        b'{"x":"\\ud800"}',
    ],
)
def test_json_parser_rejects_numeric_unicode_and_nesting_bombs(
    tmp_path: Path, document: bytes
) -> None:
    path = tmp_path / "bomb.json"
    path.write_bytes(document)
    with pytest.raises(JobValidationError, match="invalid recipe JSON"):
        load_json_mapping(path, label="recipe")


def test_json_parser_accepts_literal_escaped_backslash(tmp_path: Path) -> None:
    # A literal backslash followed by "ud800" is valid JSON Unicode text.
    path = tmp_path / "valid-escape.json"
    path.write_bytes(b'{"x":"\\\\ud800"}')
    assert load_json_mapping(path, label="recipe") == {"x": r"\\ud800"}


def test_bounded_loader_rejects_oversize_even_without_stat(tmp_path: Path) -> None:
    from dpo4000_utils.job_runner import MAX_JOB_JSON_BYTES

    path = tmp_path / "oversize.json"
    with path.open("wb") as handle:
        handle.truncate(MAX_JOB_JSON_BYTES + 1)
    with pytest.raises(JobValidationError, match="maximum"):
        load_json_mapping(path, label="recipe")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"scientific_compressed": True}, "require scientific_export_path"),
        ({"scientific_points": 0}, "positive integer"),
        ({"scientific_points": True}, "positive integer"),
        ({"timeout_ms": True}, "integer"),
        ({"timeout_ms": 600001}, "range"),
        ({"expect_idn": " "}, "non-empty"),
        ({"expect_idn": True}, "non-empty"),
        ({"scientific_export_path": Path("capture.bad")}, "Cannot infer"),
        ({"scientific_export_path": Path("capture.dpoz"), "scientific_format": "other"}, "Unsupported"),
    ],
)
def test_config_errors_preflight(tmp_path: Path, kwargs: dict, message: str) -> None:
    with pytest.raises(JobValidationError, match=message):
        JobConfig(recipe_path=_recipe(tmp_path), resource="FAKE::INSTR", **kwargs)


@pytest.mark.parametrize("method", ["_private", "probe_scpi_query", "connect", "not_a_method"])
def test_invalid_recipe_never_opens_session(tmp_path: Path, method: str) -> None:
    recorder = Recorder()
    result = recorder.runner().run(
        JobConfig(recipe_path=_recipe(tmp_path, (method,)), resource="FAKE::INSTR")
    )
    assert result.exit_code is JobExitCode.VALIDATION_ERROR
    assert (recorder.opened, recorder.closed) == (0, 0)


def test_report_cannot_overwrite_recipe_or_rules(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path)
    with pytest.raises(JobValidationError, match="must not replace"):
        JobConfig(recipe_path=recipe, resource="FAKE::INSTR", report_path=recipe)
    with pytest.raises(JobValidationError, match="must not replace"):
        JobConfig(
            recipe_path=recipe, resource="FAKE::INSTR",
            scientific_export_path=recipe, scientific_format="dpoz",
        )


def test_report_and_export_must_not_share_destination(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path)
    export = tmp_path / "output.dpoz"
    with pytest.raises(JobValidationError, match="distinct"):
        JobConfig(
            recipe_path=recipe, resource="FAKE::INSTR",
            report_path=export, scientific_export_path=export,
        )


def test_invalid_export_suffix_never_opens_session(tmp_path: Path) -> None:
    recorder = Recorder()
    with pytest.raises(JobValidationError):
        JobConfig(
            recipe_path=_recipe(tmp_path),
            resource="FAKE::INSTR",
            scientific_export_path=tmp_path / "capture.unknown",
        )
    assert recorder.opened == 0


def test_preflight_validation_only_does_not_load_qt_or_open_visa(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path, ("measure",))
    recorder = Recorder()
    result = recorder.runner().run(JobConfig(recipe_path=recipe, validate_only=True))
    assert result.exit_code is JobExitCode.SUCCESS
    assert recorder.opened == recorder.closed == 0


def test_headless_import_does_not_import_qt_in_clean_subprocess() -> None:
    check = (
        "import sys; import dpo4000_utils.job_runner; "
        "assert not any(k.startswith('PySide6') for k in sys.modules)"
    )
    finished = subprocess.run(
        [sys.executable, "-c", check], capture_output=True, text=True, check=False
    )
    assert finished.returncode == 0, finished.stderr


def test_concurrent_run_is_rejected_and_single_session_stays_owned(tmp_path: Path) -> None:
    recorder = Recorder()
    runner = recorder.runner()
    config = JobConfig(
        recipe_path=_recipe(tmp_path, ("wait_for_release",)),
        resource="FAKE::INSTR",
    )
    results = []
    thread = threading.Thread(target=lambda: results.append(runner.run(config)))
    thread.start()
    try:
        assert recorder.scope.started.wait(timeout=2)
        rejected = runner.run(config)
        assert rejected.exit_code is JobExitCode.RUNTIME_ERROR
        assert rejected.status == "runtime_error"
        assert recorder.opened == 1
    finally:
        recorder.scope.release.set()
        thread.join(timeout=3)
    assert not thread.is_alive()
    assert results[0].exit_code is JobExitCode.SUCCESS
    assert recorder.closed == 1


def test_cancel_during_active_call_prevents_next_call(tmp_path: Path) -> None:
    recorder = Recorder()
    runner = recorder.runner()
    config = JobConfig(
        recipe_path=_recipe(tmp_path, ("wait_for_release", "measure")),
        resource="FAKE::INSTR",
    )
    results = []
    worker = threading.Thread(target=lambda: results.append(runner.run(config)))
    worker.start()
    try:
        assert recorder.scope.started.wait(timeout=2)
        runner.cancel()
    finally:
        recorder.scope.release.set()
        worker.join(timeout=3)
    assert not worker.is_alive()
    assert results[0].exit_code is JobExitCode.CANCELLED
    assert results[0].status == "cancelled"
    assert recorder.scope.calls == 1
    assert (recorder.opened, recorder.closed) == (1, 1)


def test_json_report_atomic_replace_preserves_old_file_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = Recorder()
    result = recorder.runner().run(
        JobConfig(recipe_path=_recipe(tmp_path), resource="FAKE::INSTR")
    )
    dest = tmp_path / "report.json"
    dest.write_text("previous durable report", encoding="utf-8")

    def fail_replace(_src, _dest) -> None:
        raise OSError("simulated replacement failure")

    monkeypatch.setattr("dpo4000_utils.job_runner.os.replace", fail_replace)
    with pytest.raises(OSError, match="replacement"):
        write_job_report(dest, result)
    assert dest.read_text(encoding="utf-8") == "previous durable report"
    assert sorted(tmp_path.glob(".report.json.*.tmp")) == []


def test_cli_invalid_environment_returns_two_and_writes_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DPO4000_TIMEOUT_MS", "invalid")
    report = tmp_path / "result.json"
    code = main([
        "--recipe", str(_recipe(tmp_path)),
        "--validate-only", "--quiet", "--report", str(report),
    ])
    assert code == 2
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["exit_code"] == 2
    assert payload["status"] == "validation_error"


def test_cli_explicit_timeout_overrides_bad_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DPO4000_TIMEOUT_MS", "invalid")
    assert main([
        "--recipe", str(_recipe(tmp_path, ("query_identity",))),
        "--validate-only", "--quiet", "--timeout-ms", "2000",
    ]) == 0


def test_report_failure_is_runtime_error_even_when_recipe_succeeded(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path, ("query_identity",))
    target = tmp_path / "existing-directory"
    target.mkdir()
    assert main([
        "--recipe", str(recipe), "--validate-only",
        "--quiet", "--report", str(target),
    ]) == int(JobExitCode.RUNTIME_ERROR)


def test_installed_cli_validate_only_without_visa(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path, ("query_identity",))
    completed = subprocess.run(
        [sys.executable, "-m", "dpo4000_utils.job_runner",
         "--recipe", str(recipe), "--validate-only", "--quiet"],
        capture_output=True, text=True, check=False,
        env={**os.environ, "DPO4000_RESOURCE": ""},
    )
    assert completed.returncode == 0, completed.stderr
