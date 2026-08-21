"""Background worker helpers for PySide6 scope actions.

The GUI keeps the historical synchronous action API because many handlers update
widgets from the returned readback value.  The actual VISA/SCPI session work is
run on a Qt worker thread and synchronized back through a nested QEventLoop so
instrument I/O is not executed on the GUI thread.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


@dataclass(slots=True)
class WorkerResult:
    """Result container returned from a background callable."""

    value: Any = None
    error: BaseException | None = None


class ScopeWorkerSignals(QObject):
    """Signals emitted by a scope worker runnable."""

    finished = Signal(object)


class ScopeWorker(QRunnable):
    """Run a blocking callable on Qt's global worker pool."""

    def __init__(self, callback: Callable[[], Any]) -> None:
        super().__init__()
        self._callback = callback
        self.signals = ScopeWorkerSignals()

    @Slot()
    def run(self) -> None:  # pragma: no cover - exercised by runtime Qt smoke tests.
        try:
            result = WorkerResult(value=self._callback())
        except BaseException as exc:  # noqa: BLE001 - propagate exact failure to GUI thread.
            result = WorkerResult(error=exc)
        self.signals.finished.emit(result)


def start_scope_worker(callback: Callable[[], Any]) -> ScopeWorker:
    """Start *callback* on the global Qt thread pool and return the worker.

    The returned worker must be kept alive by the caller until it emits
    ``finished``.
    """

    worker = ScopeWorker(callback)
    QThreadPool.globalInstance().start(worker)
    return worker


__all__ = ["ScopeWorker", "ScopeWorkerSignals", "WorkerResult", "start_scope_worker"]
