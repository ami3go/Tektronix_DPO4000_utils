"""Background worker helpers for PySide6 scope actions.

The production GUI uses one dedicated worker thread for one retained DPO4054/VISA
session. Requests are serialized by Qt's queued connection and completed through
signals/callbacks; this module deliberately contains no nested ``QEventLoop`` wait.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event as ThreadEvent
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, Qt, Signal, Slot

from ..errors import add_exception_note, is_transport_error
from ..instrument import DPO4054


@dataclass(slots=True)
class WorkerResult:
    """Result container returned from a background callable."""

    value: Any = None
    error: BaseException | None = None
    cancelled: bool = False


class ScopeWorkerSignals(QObject):
    """Signals emitted by a one-shot scope worker runnable."""

    finished = Signal(object)


class ScopeWorker(QRunnable):
    """Run a blocking callable on Qt's global worker pool.

    This helper remains for non-session background work. Production instrument
    dispatch uses :class:`PersistentScopeSession` below.
    """

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
    """Start *callback* on the global Qt thread pool and return the worker."""

    worker = ScopeWorker(callback)
    QThreadPool.globalInstance().start(worker)
    return worker


@dataclass(slots=True)
class PersistentScopeRequest:
    """One serialized operation for the persistent instrument worker."""

    request_id: int
    resource: str = ""
    timeout_ms: int = 20_000
    callback: Callable[[Any], Any] | None = None
    close_only: bool = False
    cancel_event: ThreadEvent = field(default_factory=ThreadEvent)


@dataclass(slots=True)
class PersistentScopeCompletion:
    """Worker completion paired with the originating request id."""

    request_id: int
    result: WorkerResult


class PersistentScopeWorker(QObject):
    """Own one DPO4054 session and execute requests on one dedicated QThread."""

    finished = Signal(object)

    def __init__(self, scope_factory: Callable[..., Any] | None = None) -> None:
        super().__init__()
        self._scope_factory = scope_factory or DPO4054
        self._scope: Any = None
        self._resource = ""

    @property
    def has_open_scope(self) -> bool:
        return self._scope is not None

    def _configure_session(self, scope: Any, timeout_ms: int) -> None:
        """Apply runtime communication policy through the public driver boundary."""
        configure = getattr(scope, "configure_session", None)
        if not callable(configure):
            raise TypeError("Persistent scope object must provide configure_session().")
        configure(
            timeout_ms=int(timeout_ms),
            read_termination="\n",
            write_termination="\n",
        )

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

    def _emit(self, request: PersistentScopeRequest, result: WorkerResult) -> None:
        self.finished.emit(PersistentScopeCompletion(request.request_id, result))

    @Slot(object)
    def run_request(self, request: object) -> None:  # pragma: no cover - Qt runtime tested.
        if not isinstance(request, PersistentScopeRequest):
            self.finished.emit(
                PersistentScopeCompletion(
                    -1,
                    WorkerResult(error=TypeError("Invalid persistent scope request.")),
                )
            )
            return

        if request.cancel_event.is_set() and not request.close_only:
            self._emit(request, WorkerResult(cancelled=True))
            return

        try:
            if request.close_only:
                self._close_scope()
                result = WorkerResult()
            else:
                scope = self._ensure_scope(request.resource, request.timeout_ms)
                if request.callback is None:
                    raise ValueError("Persistent scope request requires a callback.")
                if request.cancel_event.is_set():
                    result = WorkerResult(cancelled=True)
                else:
                    value = request.callback(scope)
                    result = WorkerResult(value=value, cancelled=request.cancel_event.is_set())
        except BaseException as exc:  # noqa: BLE001 - preserve exact instrument failure.
            if not request.close_only and is_transport_error(exc):
                try:
                    self._close_scope()
                except BaseException as cleanup_exc:  # noqa: BLE001 - keep primary failure.
                    add_exception_note(exc, f"Persistent-session cleanup failure: {cleanup_exc}")
            result = WorkerResult(error=exc)

        self._emit(request, result)


class PersistentScopeSession(QObject):
    """GUI-thread facade for a dedicated worker-thread persistent scope session.

    ``submit()`` is non-blocking. Completion callbacks are invoked on this object's
    thread (normally the GUI thread) after the worker emits a queued completion.
    """

    request = Signal(object)
    completed = Signal(int, object)
    shutdown_finished = Signal(object)

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
        self.request.connect(
            self._worker.run_request,
            Qt.ConnectionType.QueuedConnection,
        )
        self._worker.finished.connect(
            self._on_worker_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        self._thread.finished.connect(self._worker.deleteLater)
        self._next_request_id = 1
        self._callbacks: dict[int, Callable[[WorkerResult], None]] = {}
        self._requests: dict[int, PersistentScopeRequest] = {}
        self._shutdown_started = False
        self._thread.start()

    @property
    def is_running(self) -> bool:
        return self._thread.isRunning()

    @property
    def has_pending_requests(self) -> bool:
        return bool(self._requests)

    def _new_request_id(self) -> int:
        request_id = self._next_request_id
        self._next_request_id += 1
        return request_id

    def submit(
        self,
        resource: str,
        timeout_ms: int,
        callback: Callable[[Any], Any],
        *,
        on_finished: Callable[[WorkerResult], None] | None = None,
    ) -> int:
        """Queue one scope operation and return its request id immediately."""
        if self._shutdown_started or not self._thread.isRunning():
            raise RuntimeError("Persistent scope worker is shutting down or not running.")
        request = PersistentScopeRequest(
            request_id=self._new_request_id(),
            resource=str(resource),
            timeout_ms=int(timeout_ms),
            callback=callback,
        )
        self._requests[request.request_id] = request
        if on_finished is not None:
            self._callbacks[request.request_id] = on_finished
        self.request.emit(request)
        return request.request_id

    def close_scope_async(
        self,
        *,
        on_finished: Callable[[WorkerResult], None] | None = None,
    ) -> int | None:
        """Queue closure of the retained instrument on its owning worker thread."""
        if not self._thread.isRunning():
            if on_finished is not None:
                on_finished(WorkerResult())
            return None
        request = PersistentScopeRequest(
            request_id=self._new_request_id(),
            close_only=True,
        )
        self._requests[request.request_id] = request
        if on_finished is not None:
            self._callbacks[request.request_id] = on_finished
        self.request.emit(request)
        return request.request_id

    def cancel(self, request_id: int) -> bool:
        """Cooperatively cancel a queued/current request when the operation permits it."""
        request = self._requests.get(int(request_id))
        if request is None or request.close_only:
            return False
        request.cancel_event.set()
        return True

    def cancel_all(self) -> None:
        """Mark every pending instrument operation cancelled."""
        for request in tuple(self._requests.values()):
            if not request.close_only:
                request.cancel_event.set()

    @Slot(object)
    def _on_worker_finished(self, completion: object) -> None:
        if not isinstance(completion, PersistentScopeCompletion):
            return
        request_id = completion.request_id
        self._requests.pop(request_id, None)
        callback = self._callbacks.pop(request_id, None)
        self.completed.emit(request_id, completion.result)
        if callback is not None:
            callback(completion.result)

    def shutdown_async(
        self,
        *,
        on_finished: Callable[[WorkerResult], None] | None = None,
    ) -> None:
        """Close the retained scope and stop the worker thread without blocking Qt."""
        if self._shutdown_started:
            if on_finished is not None:
                self.shutdown_finished.connect(on_finished, Qt.ConnectionType.SingleShotConnection)
            return
        self._shutdown_started = True
        self.cancel_all()

        if not self._thread.isRunning():
            result = WorkerResult()
            self.shutdown_finished.emit(result)
            if on_finished is not None:
                on_finished(result)
            return

        def finish_thread(result: WorkerResult) -> None:
            def emit_done() -> None:
                self.shutdown_finished.emit(result)
                if on_finished is not None:
                    on_finished(result)

            self._thread.finished.connect(emit_done, Qt.ConnectionType.SingleShotConnection)
            self._thread.quit()

        self.close_scope_async(on_finished=finish_thread)


__all__ = [
    "PersistentScopeCompletion",
    "PersistentScopeRequest",
    "PersistentScopeSession",
    "PersistentScopeWorker",
    "ScopeWorker",
    "ScopeWorkerSignals",
    "WorkerResult",
    "start_scope_worker",
]
