"""Logger L9 retention wrapper around the hardened Automation retention engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..automation.retention import (
    RetentionApplyResult,
    RetentionError,
    RetentionPlan,
    RetentionPolicy,
    apply_retention_plan,
    plan_retention,
    register_retention_event,
)

LoggerRetentionPolicy = RetentionPolicy
LoggerRetentionError = RetentionError


@dataclass
class LoggerRetentionStatistics:
    registered_segments: int = 0
    deleted_segments: int = 0
    deleted_files: int = 0
    reclaimed_bytes: int = 0
    last_plan: RetentionPlan | None = None


class LoggerRetentionManager:
    """Register only closed Logger segment groups and apply safe retention."""

    def __init__(self, root: str | Path, policy: LoggerRetentionPolicy) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.policy = policy
        self.statistics = LoggerRetentionStatistics()
        self._seen_events: set[str] = set()

    @staticmethod
    def _event_id(paths: Iterable[Path]) -> str:
        names = sorted(Path(path).name for path in paths)
        if not names:
            raise LoggerRetentionError("A Logger retention segment must contain files.")
        return "logger-segment:" + "|".join(names)

    def register_closed_segment(self, paths: Iterable[str | Path]) -> None:
        normalized = tuple(Path(path).expanduser() for path in paths)
        event_id = self._event_id(normalized)
        if event_id in self._seen_events:
            return
        register_retention_event(self.root, event_id, normalized)
        self._seen_events.add(event_id)
        self.statistics.registered_segments += 1

    def register_closed_segments(
        self,
        segments: Iterable[Iterable[str | Path]],
    ) -> None:
        for segment in segments:
            self.register_closed_segment(segment)

    def apply(self) -> tuple[RetentionPlan, RetentionApplyResult]:
        plan = plan_retention(self.root, self.policy)
        self.statistics.last_plan = plan
        if not plan.satisfied:
            detail = "; ".join(plan.diagnostics) or "retention policy cannot be satisfied"
            raise LoggerRetentionError(detail)
        result = apply_retention_plan(self.root, plan)
        self.statistics.deleted_segments += result.deleted_events
        self.statistics.deleted_files += result.deleted_files
        self.statistics.reclaimed_bytes += result.reclaimed_bytes
        return plan, result


__all__ = [
    "LoggerRetentionError",
    "LoggerRetentionManager",
    "LoggerRetentionPolicy",
    "LoggerRetentionStatistics",
]
