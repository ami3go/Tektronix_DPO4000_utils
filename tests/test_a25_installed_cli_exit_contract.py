"""Exercise all A25 exit codes through the actual installed dpo4000-job script.

The child process injects a deterministic fake VISA session using sitecustomize;
no physical instrument or real VISA resource is accessed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import pytest


_SITE_CUSTOMIZE = '''
import os
from contextlib import contextmanager
from pathlib import Path

import dpo4000_utils.job_runner as job_runner


class FakeScope:
    def __init__(self, *_args, **_kwargs):
        pass

    def query_identity(self):
        flag = os.getenv("A25_FAKE_OPEN_FLAG")
        if flag:
            Path(flag).touch()
        if os.getenv("A25_FAKE_SCENARIO") == "runtime":
            return "UNKNOWN,UNKNOWN,FAKE,0"
        return "TEKTRONIX,DPO4054,FAKE,0"

    def get_trigger_holdoff(self):
        if os.getenv("A25_FAKE_SCENARIO") == "recipe":
            raise RuntimeError("synthetic recipe failure")
        return 0.5

    def read_enabled_waveforms(self, *, point_count=None):
        raise RuntimeError("synthetic scientific export failure")


@contextmanager
def fake_session(_resource, **_kwargs):
    yield FakeScope()


OriginalRunner = job_runner.HeadlessJobRunner


class FakeRunner(OriginalRunner):
    def __init__(self):
        super().__init__(
            session_factory=fake_session,
            validation_target_factory=FakeScope,
        )


job_runner.HeadlessJobRunner = FakeRunner
'''


def _installed_cli() -> str:
    command = shutil.which("dpo4000-job")
    if not command:
        pytest.skip("dpo4000-job is not installed in this environment")
    return command


def _write_json(path: Path, document: dict) -> Path:
    path.write_text(json.dumps(document) + "\n", encoding="utf-8")
    return path


def _case_files(tmp_path: Path, *, method: str = "get_trigger_holdoff") -> tuple[Path, Path]:
    recipe = _write_json(
        tmp_path / "recipe.json",
        {
            "version": 1,
            "name": "installed CLI test",
            "steps": [{"kind": "call", "name": "HOLDOFF", "method": method}],
        },
    )
    return recipe, tmp_path / "report.json"


def _child_env(tmp_path: Path, scenario: str) -> dict[str, str]:
    (tmp_path / "sitecustomize.py").write_text(_SITE_CUSTOMIZE, encoding="utf-8")
    return {
        **os.environ,
        "PYTHONPATH": str(tmp_path) + os.pathsep + os.environ.get("PYTHONPATH", ""),
        "A25_FAKE_SCENARIO": scenario,
        "DPO4000_RESOURCE": "",
        "DPO4000_TIMEOUT_MS": "20000",
        "DPO4000_EXPECT_IDN": "TEKTRONIX,DPO4054",
    }


@pytest.mark.parametrize(
    ("scenario", "expected_exit", "expected_status"),
    [
        ("success", 0, "completed"),
        ("validation", 2, "validation_error"),
        ("runtime", 3, "runtime_error"),
        ("recipe", 4, "recipe_failed"),
        ("rule_fail", 5, "rule_failed"),
        ("rule_invalid", 6, "rule_invalid"),
        ("export", 7, "export_error"),
    ],
)
def test_all_normal_exit_codes_via_installed_cli(
    tmp_path: Path, scenario: str, expected_exit: int, expected_status: str
) -> None:
    command = _installed_cli()
    recipe, report = _case_files(
        tmp_path, method="probe_scpi_query" if scenario == "validation" else "get_trigger_holdoff"
    )
    args = [
        command, "--recipe", str(recipe), "--resource", "FAKE::INSTR",
        "--report", str(report), "--quiet",
    ]
    if scenario in ("rule_fail", "rule_invalid"):
        rules = _write_json(
            tmp_path / "rules.json",
            {
                "version": 1,
                "name": "holdoff limit",
                "root": {
                    "type": "compare",
                    "id": "holdoff_check",
                    "input": "UNDEFINED" if scenario == "rule_invalid" else "HOLDOFF",
                    "operator": ">=",
                    "value": 1.0,
                },
            },
        )
        args += ["--rules", str(rules)]
    if scenario == "export":
        args += ["--export", str(tmp_path / "capture.npz")]
    child = subprocess.run(
        args,
        env=_child_env(tmp_path, scenario),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert child.returncode == expected_exit, (child.stdout, child.stderr)
    result = json.loads(report.read_text(encoding="utf-8"))
    assert (result["exit_code"], result["status"]) == (expected_exit, expected_status)
    assert (result["schema"], result["version"]) == ("dpo4000-headless-job", 1)
    assert child.stdout == ""


@pytest.mark.skipif(os.name == "nt", reason="POSIX process SIGINT test")
def test_cancelled_exit_130_via_installed_cli(tmp_path: Path) -> None:
    command = _installed_cli()
    recipe = _write_json(
        tmp_path / "recipe.json",
        {
            "version": 1,
            "name": "cancel installed CLI",
            "steps": [{"kind": "delay", "name": "long delay", "seconds": 10.0}],
        },
    )
    report = tmp_path / "report.json"
    opened = tmp_path / "session-opened"
    env = _child_env(tmp_path, "cancel")
    env["A25_FAKE_OPEN_FLAG"] = str(opened)
    child = subprocess.Popen(
        [
            command, "--recipe", str(recipe), "--resource", "FAKE::INSTR",
            "--report", str(report), "--quiet",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10.0
        while not opened.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert opened.exists(), "installed CLI did not open its fake session"
        child.send_signal(signal.SIGINT)
        stdout, stderr = child.communicate(timeout=10)
        assert child.returncode == 130, (stdout, stderr)
        result = json.loads(report.read_text(encoding="utf-8"))
        assert result["exit_code"] == 130
        assert result["status"] == "cancelled"
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=5)
