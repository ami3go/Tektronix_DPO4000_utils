from __future__ import annotations

from pathlib import Path

import pytest

from dpo4000_utils.logger.retention import (
    LoggerRetentionError,
    LoggerRetentionManager,
    LoggerRetentionPolicy,
)


def _write(path: Path, size: int = 16) -> Path:
    path.write_bytes(b"x" * size)
    return path


def test_logger_retention_deletes_oldest_closed_segment(tmp_path: Path) -> None:
    root = tmp_path / "logger"
    root.mkdir()
    first = _write(root / "logger_run_0000.csv")
    second = _write(root / "logger_run_0001.csv")
    manager = LoggerRetentionManager(root, LoggerRetentionPolicy(keep_last_events=1))
    manager.register_closed_segment((first,))
    manager.register_closed_segment((second,))

    plan, result = manager.apply()

    assert plan.satisfied
    assert result.deleted_events == 1
    assert not first.exists()
    assert second.exists()


def test_logger_retention_rejects_file_outside_logger_root(tmp_path: Path) -> None:
    root = tmp_path / "logger"
    root.mkdir()
    outside = _write(tmp_path / "outside.csv")
    manager = LoggerRetentionManager(root, LoggerRetentionPolicy(keep_last_events=1))

    with pytest.raises(LoggerRetentionError):
        manager.register_closed_segment((outside,))
