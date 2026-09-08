from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from dpo4000_utils.bench_hil import (
    AutomationLoggerHilRunner,
    HilConfig,
    HilSkip,
)


def _runner(tmp_path: Path) -> AutomationLoggerHilRunner:
    return AutomationLoggerHilRunner(
        HilConfig(
            resource="TCPIP0::192.0.2.1::INSTR",
            output_dir=tmp_path,
            hardcopy=False,
        )
    )


def test_hil_config_rejects_invalid_channel_and_suite(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        HilConfig(resource="x", output_dir=tmp_path, channel=0)
    with pytest.raises(ValueError):
        HilConfig(resource="x", output_dir=tmp_path, suite="unknown")


def test_case_results_are_independent_and_failures_keep_tracebacks(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    runner._case("pass", "Pass", "test", lambda: "worked")
    runner._case("skip", "Skip", "test", lambda: (_ for _ in ()).throw(HilSkip("not applicable")))
    runner._case("fail", "Fail", "test", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    assert [result.status for result in runner.results] == ["PASS", "SKIP", "FAIL"]
    failed = runner.results[-1]
    traceback_path = runner.root / failed.traceback_path
    assert traceback_path.is_file()
    assert "RuntimeError: boom" in traceback_path.read_text(encoding="utf-8")


def test_report_and_zip_are_uploadable_and_zip_does_not_contain_itself(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    runner.idn = "TEKTRONIX,DPO4054,TEST,FW"
    runner._case("pass", "Pass", "test", lambda: "worked")
    runner._write_environment_snapshot()
    runner._write_report()
    bundle = runner._zip()

    assert bundle.is_file()
    assert bundle.parent == runner.root.parent
    assert not bundle.is_relative_to(runner.root)
    report = json.loads((runner.root / "hil_report.json").read_text(encoding="utf-8"))
    assert report["counts"]["PASS"] == 1
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
    assert "hil_report.json" in names
    assert "hil_run.log" in names
    assert "environment.json" in names
    assert all(not name.endswith("_diagnostic_bundle.zip") for name in names)
