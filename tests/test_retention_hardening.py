from __future__ import annotations

from pathlib import Path

import pytest

from dpo4000_utils.automation.retention import (
    RetentionError,
    RetentionPolicy,
    apply_retention_plan,
    load_retention_index,
    plan_retention,
    register_retention_event,
)


def _file(root: Path, name: str, size: int = 16) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def test_retention_owner_namespaces_cannot_delete_each_other(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    automation = _file(root, "automation.bin", 10)
    logger = _file(root, "logger.bin", 20)
    register_retention_event(root, "a1", [automation], owner="automation")
    register_retention_event(root, "l1", [logger], owner="logger")

    plan = plan_retention(
        root,
        RetentionPolicy(max_bytes=0),
        owner="automation",
        free_bytes_override=1000,
    )
    assert [entry.event_id for entry in plan.deletions] == ["a1"]
    apply_retention_plan(root, plan)

    assert not automation.exists()
    assert logger.exists()
    events = load_retention_index(root).events
    assert [(event.owner, event.event_id) for event in events] == [("logger", "l1")]


def test_retention_staging_failure_rolls_back_files_and_index(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "root"
    root.mkdir()
    first = _file(root, "first.bin", 10)
    second = _file(root, "second.bin", 20)
    register_retention_event(root, "event", [first, second])
    before = load_retention_index(root)
    plan = plan_retention(root, RetentionPolicy(max_bytes=0), free_bytes_override=1000)

    import dpo4000_utils.automation.retention as retention

    real_replace = retention.os.replace
    calls = 0

    def flaky_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated second staging rename failure")
        return real_replace(source, destination)

    monkeypatch.setattr(retention.os, "replace", flaky_replace)
    with pytest.raises(RetentionError, match="rolled back"):
        apply_retention_plan(root, plan)

    assert first.exists() and second.exists()
    assert load_retention_index(root) == before
