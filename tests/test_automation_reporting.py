from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from dpo4000_utils.automation.reporting import AutomationRunReporter, make_event_record


def test_a12_events_are_durable_before_final_summary(tmp_path: Path) -> None:
    reporter = AutomationRunReporter(
        root=tmp_path,
        mode="Periodic Image",
        config={"mode": "Periodic Image"},
        resource="USB::TEST",
        idn="TEK,DPO4054,TEST,1",
        package_version="test",
    )
    started = datetime.now(timezone.utc)
    event = make_event_record(
        sequence=1,
        description="Automation image #0001",
        cause="periodic",
        status="success",
        started_at=started,
        ended_at=started,
        artifact_paths=(str(tmp_path / "screen.png"),),
    )
    reporter.append_event(event)
    assert reporter.event_jsonl_path.exists()
    assert reporter.event_csv_path.exists()
    assert reporter.summary_path.exists() is False
    payload = json.loads(reporter.event_jsonl_path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["event_id"] == "event-00000001"
    assert payload["artifact_paths"] == [str(tmp_path / "screen.png")]


def test_a12_finalize_is_atomic_and_idempotent(tmp_path: Path) -> None:
    reporter = AutomationRunReporter(
        root=tmp_path,
        mode="Burst Capture",
        config={"mode": "Burst Capture"},
    )
    first = reporter.finalize(
        stop_reason="count_limit",
        counters={"succeeded": 10, "failed": 0, "partial": 0},
        recovery={"reconnects": 1},
        retention={"last_reclaimed_bytes": 1024},
    )
    second = reporter.finalize(
        stop_reason="should-not-rewrite",
        counters={"succeeded": 999},
    )
    assert first == second
    summary = json.loads(first.read_text(encoding="utf-8"))
    assert summary["stop_reason"] == "count_limit"
    assert summary["counters"]["succeeded"] == 10
    assert summary["recovery"]["reconnects"] == 1


def test_a12_gui_reports_automation_only_and_has_no_raw_scope_io() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "dpo4000_utils" / "gui_qt" / "automation_report_window.py").read_text(
        encoding="utf-8"
    )
    assert "_REPORT_OPERATION_PREFIXES" in source
    assert "AutomationRunReporter" in source
    assert "_finalize_automation_report" in source
    assert '"application_close"' in source
    assert "event_jsonl" not in source  # storage details stay framework-neutral
    assert ".query(" not in source
    assert ".write(" not in source
