from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dpo4000_utils.automation import (
    RetentionError,
    RetentionPolicy,
    apply_retention_plan,
    load_retention_index,
    plan_retention,
    register_retention_event,
)
from dpo4000_utils.automation.retention import RETENTION_INDEX_FILENAME


def _file(root: Path, name: str, size: int = 16) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def test_a9_registration_rejects_artifact_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = _file(tmp_path, "outside.bin")
    with pytest.raises(RetentionError, match="outside output root"):
        register_retention_event(root, "event-1", [outside])


def test_a9_registration_rejects_symlink_artifact(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = _file(root, "target.bin")
    link = root / "link.bin"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(RetentionError, match="symlink"):
        register_retention_event(root, "event-1", [link])


def test_a9_dry_run_and_count_policy_delete_oldest_complete_event(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    old = _file(root, "old.png", 10)
    new = _file(root, "new.png", 20)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    register_retention_event(root, "old", [old], completed_utc=t0)
    register_retention_event(root, "new", [new], completed_utc=t0 + timedelta(seconds=1))

    plan = plan_retention(root, RetentionPolicy(keep_last_events=1), free_bytes_override=1000)
    assert [entry.event_id for entry in plan.deletions] == ["old"]
    assert old.exists() and new.exists(), "preview must never delete"

    result = apply_retention_plan(root, plan)
    assert result.deleted_events == 1
    assert result.deleted_files == 1
    assert result.reclaimed_bytes == 10
    assert old.exists() is False
    assert new.exists() is True
    assert [event.event_id for event in load_retention_index(root).events] == ["new"]


def test_a9_age_then_count_then_size_order_is_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    paths = [_file(root, f"e{i}.bin", 100) for i in range(4)]
    for i, path in enumerate(paths):
        register_retention_event(
            root,
            f"e{i}",
            [path],
            completed_utc=now - timedelta(days=10 - i),
        )
    plan = plan_retention(
        root,
        RetentionPolicy(keep_last_events=2, max_bytes=100, max_age_s=8 * 86400),
        now_utc=now,
        free_bytes_override=1000,
    )
    assert [entry.event_id for entry in plan.deletions] == ["e0", "e1", "e2"]
    assert plan.bytes_to_reclaim == 300
    assert plan.satisfied is True


def test_a9_protected_event_is_never_planned_for_deletion(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    active = _file(root, "active.csv", 50)
    other = _file(root, "other.csv", 50)
    now = datetime.now(timezone.utc)
    register_retention_event(root, "active", [active], completed_utc=now - timedelta(days=2))
    register_retention_event(root, "other", [other], completed_utc=now - timedelta(days=1))
    plan = plan_retention(
        root,
        RetentionPolicy(keep_last_events=1),
        protected_paths=[active],
        free_bytes_override=1000,
    )
    assert all("active.csv" not in entry.files for entry in plan.deletions)
    assert active.exists()


def test_a9_malformed_parent_path_in_index_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    payload = {
        "schema_version": 1,
        "events": [
            {
                "event_id": "bad",
                "completed_utc": datetime.now(timezone.utc).isoformat(),
                "files": ["../outside.txt"],
            }
        ],
    }
    (root / RETENTION_INDEX_FILENAME).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RetentionError, match="Unsafe retention path"):
        load_retention_index(root)


def test_a9_symlink_swap_after_preview_fails_before_delete(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    owned = _file(root, "owned.bin", 10)
    outside = _file(tmp_path, "outside.bin", 10)
    register_retention_event(root, "event", [owned])
    plan = plan_retention(root, RetentionPolicy(max_bytes=0), free_bytes_override=1000)
    owned.unlink()
    try:
        owned.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(RetentionError):
        apply_retention_plan(root, plan)
    assert outside.exists()


def test_a9_minimum_free_space_reports_unsatisfied_when_protected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    active = _file(root, "active.bin", 100)
    register_retention_event(root, "active", [active])
    plan = plan_retention(
        root,
        RetentionPolicy(min_free_bytes=1000),
        protected_paths=[active],
        free_bytes_override=100,
    )
    assert plan.deletions == ()
    assert plan.satisfied is False
    assert any("minimum-free-space" in text for text in plan.diagnostics)


def test_a9_gui_requires_preview_and_defers_active_measurement_log() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "dpo4000_utils" / "gui_qt" / "automation_retention_window.py").read_text(
        encoding="utf-8"
    )
    assert "Preview retention" in source
    assert "setEnabled(False)" in source
    assert "_retention_preview_ack" in source
    assert "MEASUREMENT_LOGGER_MODE" in source
    assert "_register_measurement_log_after_stop" in source
    assert "Output folder changed during the active automation run" in source
    assert ".query(" not in source
    assert ".write(" not in source
