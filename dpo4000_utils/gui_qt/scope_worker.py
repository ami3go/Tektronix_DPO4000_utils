"""Background worker helpers for PySide6 scope actions.

The GUI keeps the historical synchronous action API because many handlers update
widgets from the returned readback value. Short-lived actions continue to use the
global Qt worker pool. Optional persistent sessions use one dedicated QThread so
one DPO4054/VISA session is created, used, and closed on the same worker thread.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import (
    QEventLoop,
    QObject,
    QRunnable,
    QThread,
    QThreadPool,
    Qt,
    QTimer,
    Signal,
    Slot,
)

from ..errors import add_exception_note, is_transport_error
from ..instrument import DPO4054


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


def start_scope_worker(
    callback: Callable[[], Any],
    *,
    on_finished: Callable[[object], None] | None = None,
) -> ScopeWorker:
    """Start *callback* on the global Qt thread pool and return the worker.

    Pass ``on_finished`` rather than connecting to ``worker.signals.finished``
    after this returns: a fast callback can complete before the caller connects,
    and the resulting emission would be delivered to nobody. A caller waiting on
    a nested event loop would then never be woken.
    """

    worker = ScopeWorker(callback)
    if on_finished is not None:
        worker.signals.finished.connect(on_finished)
    QThreadPool.globalInstance().start(worker)
    return worker


@dataclass(slots=True)
class PersistentScopeRequest:
    """One serialized operation for the persistent instrument worker."""

    resource: str = ""
    timeout_ms: int = 20_000
    callback: Callable[[Any], Any] | None = None
    close_only: bool = False


class PersistentScopeWorker(QObject):
    """Own one DPO4054 session and execute requests on one dedicated QThread."""

    finished = Signal(object)

    def __init__(self, scope_factory: Callable[..., Any] | None = None) -> None:
        super().__init__()
        self._scope_factory = scope_factory or DPO4054
        self._scope: Any = None
        self._resource = ""

    def _configure_session(self, scope: Any, timeout_ms: int) -> None:
        instrument = scope.ensure_connected()
        instrument.timeout = int(timeout_ms)
        instrument.write_termination = "\n"
        instrument.read_termination = "\n"

    def _close_scope(self) -> None:
        scope = self._scope
        self._scope = None
        self._resource = ""
        if scope is not None:
            scope.disconnect()

    def _ensure_scope(self, resource: str, timeout_ms: int) -> Any:
        resource = str(resource).strip()
        if not resource:
            raise ValueError("VISA resource cannot be empty.")

        if self._scope is not None and self._resource != resource:
            self._close_scope()

        if self._scope is None:
            scope = self._scope_factory(
                resource,
                auto_connect=False,
                timeout_ms=int(timeout_ms),
                read_termination="\n",
                write_termination="\n",
            )
            scope.connect()
            self._scope = scope
            self._resource = resource

        self._configure_session(self._scope, timeout_ms)
        return self._scope

    @Slot(object)
    def run_request(self, request: object) -> None:  # pragma: no cover - Qt runtime tested.
        if not isinstance(request, PersistentScopeRequest):
            self.finished.emit(WorkerResult(error=TypeError("Invalid persistent scope request.")))
            return

        try:
            if request.close_only:
                self._close_scope()
                result = WorkerResult()
            else:
                scope = self._ensure_scope(request.resource, request.timeout_ms)
                if request.callback is None:
                    raise ValueError("Persistent scope request requires a callback.")
                result = WorkerResult(value=request.callback(scope))
        except BaseException as exc:  # noqa: BLE001 - preserve exact instrument failure.
            if not request.close_only and is_transport_error(exc):
                try:
                    self._close_scope()
                except BaseException as cleanup_exc:  # noqa: BLE001 - keep primary failure.
                    add_exception_note(exc, f"Persistent-session cleanup failure: {cleanup_exc}")
            result = WorkerResult(error=exc)

        self.finished.emit(result)


class PersistentScopeSession(QObject):
    """GUI-thread facade for a dedicated worker-thread persistent scope session."""

    request = Signal(object)

    def __init__(
        self,
        *,
        scope_factory: Callable[..., Any] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._thread = QThread()
        self._worker = PersistentScopeWorker(scope_factory=scope_factory)
        self._worker.moveToThread(self._thread)
        self._busy = False
        self.request.connect(
            self._worker.run_request,
            Qt.ConnectionType.QueuedConnection,
        )
        self._thread.start()

    def _wait_for(self, request: PersistentScopeRequest) -> WorkerResult:
        """Send one request and wait for its result on a nested event loop.

        The wait is re-entrant by construction -- the nested loop keeps dispatching
        GUI events, so a caller can arrive here again before the first request has
        finished. That is refused rather than served: each call connects its own
        handler, the earlier one is still connected, and a single completion would
        wake both, handing the inner caller the outer request's result. The worker
        serialises requests anyway, so there is nothing to gain by allowing it.
        """
        if not self._thread.isRunning():
            return WorkerResult(error=RuntimeError("Persistent scope worker is not running."))
        if self._busy:
            return WorkerResult(
                error=RuntimeError(
                    "Persistent scope session is already executing a request; "
                    "it serialises operations and cannot be re-entered."
                )
            )

        loop = QEventLoop()
        box: dict[str, WorkerResult | None] = {"result": None}

        def on_finished(result: object) -> None:
            box["result"] = result if isinstance(result, WorkerResult) else WorkerResult(value=result)
            loop.quit()

        self._busy = True
        self._worker.finished.connect(on_finished)
        try:
            self.request.emit(request)
            # on_finished runs on the worker thread, so the result can already be in
            # before the loop is entered; quit() called that early would be lost and
            # strand the wait. The timer bounds the same window around exec() itself.
            if box["result"] is None:
                settled = QTimer()
                settled.setInterval(25)
                settled.timeout.connect(lambda: loop.quit() if box["result"] is not None else None)
                settled.start()
                try:
                    loop.exec()
                finally:
                    settled.stop()
        finally:
            self._busy = False
            try:
                self._worker.finished.disconnect(on_finished)
            except (RuntimeError, TypeError):
                pass

        result = box["result"]
        if result is None:
            return WorkerResult(error=RuntimeError("Persistent scope worker finished without result."))
        return result

    def execute(
        self,
        resource: str,
        timeout_ms: int,
        callback: Callable[[Any], Any],
    ) -> WorkerResult:
        """Execute one callback, opening the session lazily and reusing it afterwards."""

        return self._wait_for(
            PersistentScopeRequest(
                resource=resource,
                timeout_ms=int(timeout_ms),
                callback=callback,
            )
        )

    def close_scope(self) -> WorkerResult:
        """Close the retained instrument session on its owning worker thread."""

        if not self._thread.isRunning():
            return WorkerResult()
        return self._wait_for(PersistentScopeRequest(close_only=True))

    def shutdown(self, timeout_ms: int = 5_000) -> WorkerResult:
        """Close the retained scope and stop the dedicated worker thread."""

        if not self._thread.isRunning():
            return WorkerResult()

        result = self.close_scope()
        self._thread.quit()
        if not self._thread.wait(max(1, int(timeout_ms))):
            return WorkerResult(error=RuntimeError("Persistent scope worker did not stop cleanly."))
        return result


__all__ = [
    "PersistentScopeRequest",
    "PersistentScopeSession",
    "PersistentScopeWorker",
    "ScopeWorker",
    "ScopeWorkerSignals",
    "WorkerResult",
    "start_scope_worker",
]
