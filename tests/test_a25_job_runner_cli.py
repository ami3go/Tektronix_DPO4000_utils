"""Exercise the real A25 CLI entry point and SIGINT policy in a child process."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest


@pytest.mark.skipif(os.name == "nt", reason="POSIX SIGINT process semantics")
def test_first_sigint_cancels_job_and_closes_session(tmp_path: Path) -> None:
    recipe = tmp_path / "recipe.json"
    recipe.write_text(
        json.dumps({
            "version": 1,
            "name": "slow read-only delay",
            "steps": [{"kind": "delay", "name": "delay", "seconds": 4.0}],
        }),
        encoding="utf-8",
    )
    report = tmp_path / "report.json"
    opened = tmp_path / "open"
    closed = tmp_path / "closed"

    child = """
import sys
from contextlib import contextmanager
from pathlib import Path
import dpo4000_utils.job_runner as mod

recipe, report, opened, closed = map(Path, sys.argv[1:])

class FakeScope:
    def __init__(self, *_args, **_kwargs):
        pass

    def query_identity(self):
        return "TEKTRONIX,DPO4054,FAKE,0"

@contextmanager
def session(_resource, **_kwargs):
    opened.touch()
    try:
        yield FakeScope()
    finally:
        closed.touch()

OriginalRunner = mod.HeadlessJobRunner

class CLIInjectedRunner(OriginalRunner):
    def __init__(self):
        super().__init__(
            session_factory=session,
            validation_target_factory=FakeScope,
        )

mod.HeadlessJobRunner = CLIInjectedRunner
raise SystemExit(mod.main([
    "--recipe", str(recipe),
    "--resource", "FAKE::INSTR",
    "--report", str(report),
    "--quiet",
]))
"""
    process = subprocess.Popen(
        [sys.executable, "-c", child, str(recipe), str(report), str(opened), str(closed)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10.0
        while not opened.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert opened.exists(), "fake session never opened"
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=6)
        assert process.returncode == 130, (stdout, stderr)
        assert closed.exists()
        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["exit_code"] == 130
        assert payload["status"] == "cancelled"
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


def test_module_cli_help_has_required_options() -> None:
    finished = subprocess.run(
        [sys.executable, "-m", "dpo4000_utils.job_runner", "--help"],
        capture_output=True, text=True, check=False,
    )
    assert finished.returncode == 0, finished.stderr
    for option in (
        "--recipe", "--rules", "--resource", "--report", "--validate-only",
        "--timeout-ms", "--expect-idn", "--export", "--export-format",
        "--export-points", "--export-compressed", "--quiet",
    ):
        assert option in finished.stdout
