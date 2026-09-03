from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from dpo4000_utils.logger.reporting import LoggerRunReporter
from dpo4000_utils.logger.retention import LoggerRetentionManager, LoggerRetentionPolicy


def _state() -> dict:
    return {
        "logger_state": "Running",
        "records": {
            "produced": 10,
            "written": 9,
            "skipped": 2,
            "dropped": 1,
            "errors": 0,
        },
        "payload_totals": {
            "waveform_points": 1000,
            "waveform_payload_bytes": 2000,
            "measurement_rows": 10,
            "measurement_values": 20,
            "bus_events": 3,
        },
        "throughput": {"disk_bytes_per_s": 123.0},
        "writer": {"peak_records": 4, "peak_bytes": 4096},
        "output_segments": [["logger_0000.csv"], ["logger_0001.csv"]],
        "recovery": {"reconnects": 1, "retry_attempts": 2},
        "retention": {"deleted_segments": 1, "reclaimed_bytes": 100},
        "reconciliation": {"records_reconciled": True},
        "last_error": "",
    }


def test_l14_checkpoint_survives_before_finalization(tmp_path: Path) -> None:
    started = datetime(2026, 9, 3, 20, 0, tzinfo=timezone.utc)
    reporter = LoggerRunReporter(
        tmp_path,
        config={"mode": "Waveform records", "waveform_sources": ["CH1"]},
        package_version="0.6.57",
        profile_name="Burn-in",
        resource="TCPIP::scope",
        idn="TEKTRONIX,DPO4054,...",
        started_at=started,
    )
    reporter.append_event("RUN_STARTED", details={"mode": "Waveform records"})
    checkpoint = reporter.checkpoint(_state(), reason="periodic")

    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert payload["status"] == "running"
    assert payload["profile_name"] == "Burn-in"
    assert payload["resource"] == "TCPIP::scope"
    assert payload["started_utc"].endswith("+00:00")
    assert payload["started_local"]
    assert payload["state"]["records"]["written"] == 9
    assert not reporter.finalized
    assert not reporter.summary_path.exists()

    jsonl_rows = reporter.event_jsonl_path.read_text(encoding="utf-8").splitlines()
    assert len(jsonl_rows) == 1
    assert json.loads(jsonl_rows[0])["event_type"] == "RUN_STARTED"
    with reporter.event_csv_path.open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    assert len(csv_rows) == 1
    assert csv_rows[0]["event_type"] == "RUN_STARTED"


def test_l14_finalize_is_atomic_idempotent_and_preserves_reconciliation(tmp_path: Path) -> None:
    reporter = LoggerRunReporter(
        tmp_path,
        config={"mode": "Measurements", "measurement_slots": [1, 2]},
        package_version="0.6.57",
    )
    reporter.checkpoint(_state(), reason="run_started")
    reporter.append_event("RUN_END", details={"stop_reason": "operator_stop"})
    summary = reporter.finalize(
        stop_reason="operator_stop",
        state=_state(),
        final_error="",
    )
    same = reporter.finalize(
        stop_reason="must_not_replace",
        state={"unexpected": True},
        final_error="changed",
    )

    assert same == summary
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["status"] == "final"
    assert payload["stop_reason"] == "operator_stop"
    assert payload["state"]["reconciliation"]["records_reconciled"] is True
    assert payload["state"]["payload_totals"]["waveform_points"] == 1000
    assert payload["ended_utc"].endswith("+00:00")
    assert payload["ended_local"]
    assert payload["event_count"] == 1
    assert reporter.finalized


def test_l14_retention_exposes_complete_registered_segment_manifest(tmp_path: Path) -> None:
    root = tmp_path / "logger"
    root.mkdir()
    first = root / "logger_0000.csv"
    second = root / "logger_0001.dpo4log"
    first.write_text("a", encoding="utf-8")
    second.write_bytes(b"b")
    manager = LoggerRetentionManager(root, LoggerRetentionPolicy())

    manager.register_closed_segment((first, second))
    manager.register_closed_segment((first, second))

    assert manager.statistics.registered_segments == 1
    assert manager.registered_segments == ((first, second),)
