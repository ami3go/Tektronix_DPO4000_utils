"""Stable launched PySide6 window for the DPO4000 GUI.

This module is the public launch target for ``dpo4000-gui-qt``.  It keeps the
mature top-menu/collapsible-card UI behavior from the testing layers, and adds a
worker-backed scope action path so VISA/SCPI I/O is not executed directly on the
Qt GUI thread.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QEventLoop, QTimer

from ..instrument import DPO4054
from .collapsible_window import (
    CONNECTION_PAGE_INDEX,
    CONTROL_PAGE_BUILDERS,
    PREFERENCE_PAGE_INDEXES,
    PREVIEW_CONTROL_GUTTER_QSS,
    PREVIEW_CONTROL_GUTTER_WIDTH,
    SETTINGS_PAGE_INDEX,
    TRIGGER_PAGE_INDEX,
    WINDOW_TITLE,
    CollapsibleCard,
    QtScopeWindow as MatureQtScopeWindow,
)
from .scope_worker import WorkerResult, start_scope_worker


class QtScopeWindow(MatureQtScopeWindow):
    """Stable launched Qt window with worker-threaded scope actions."""

    def _reject_reentrant_scope_action(self, description: str) -> bool:
        """Return True when *description* must be refused because one is in flight.

        Disabling scope-action buttons does not cover every caller: shortcuts are
        not buttons, and a handler whose callback is classified neither as a scope
        action nor as safe UI is never registered for disabling at all. Since
        ``_run_action`` waits in a nested event loop that keeps dispatching input,
        the last line of defence belongs here, where re-entry would actually open a
        second instrument session.
        """
        if not getattr(self, "_operation_active", False):
            return False
        self._append_log(f"Ignored while another operation is running: {description}")
        self.statusBar().showMessage(f"{description} ignored; a scope operation is already running")
        return True

    def _run_action(self, description: str, callback: Callable[[Any], object]) -> object | None:
        """Run a scope action through a Qt worker thread while preserving return values.

        Parent UI code historically expects ``_run_action`` to return readback
        data synchronously.  To avoid a risky rewrite of all handlers at once,
        this method snapshots GUI state, executes the blocking VISA/SCPI session
        in ``ScopeWorker``, and waits using a nested ``QEventLoop``.  The GUI
        thread remains free to repaint/process Qt events, while the instrument
        I/O itself does not run on the GUI thread.
        """
        if self._reject_reentrant_scope_action(description):
            return None
        self._operation_active = True
        self._last_action = description
        self.statusBar().showMessage(description)
        self._append_log(description)
        self._update_scope_control_enabled()
        self._update_status_strip()

        try:
            resource = self._selected_resource()
            timeout_ms = self._timeout()
        except Exception as exc:  # noqa: BLE001 - show exact GUI validation failure.
            return self._finish_scope_action_error(description, exc)

        loop = QEventLoop(self)
        box: dict[str, WorkerResult | None] = {"result": None}

        def on_finished(result: object) -> None:
            box["result"] = result if isinstance(result, WorkerResult) else WorkerResult(value=result)
            loop.quit()

        # The handler must be connected before the worker starts, and the loop must
        # not be entered once the result is already in. A callback that fails fast --
        # pyvisa missing, so connect() raises immediately -- otherwise finishes before
        # the GUI thread reaches loop.exec(), and the wakeup is lost for good.
        worker = start_scope_worker(
            lambda: self._run_snapshot_scope_session(resource, timeout_ms, callback),
            on_finished=on_finished,
        )
        self._active_scope_worker = worker
        if box["result"] is None:
            # Bound the wait so a result landing between the check above and exec()
            # below cannot strand the loop either.
            settled = QTimer()
            settled.setInterval(25)
            settled.timeout.connect(lambda: loop.quit() if box["result"] is not None else None)
            settled.start()
            try:
                loop.exec()
            finally:
                settled.stop()
        self._active_scope_worker = None

        result = box["result"]
        if result is None:
            return self._finish_scope_action_error(description, RuntimeError("Scope worker finished without result."))
        if result.error is not None:
            return self._finish_scope_action_error(description, result.error)
        return self._finish_scope_action_success(description, result.value)

    @staticmethod
    def _run_snapshot_scope_session(
        resource: str,
        timeout_ms: int,
        callback: Callable[[DPO4054], object],
    ) -> object:
        """Open a scope session using GUI-state snapshots captured on the GUI thread."""
        scope = DPO4054(resource, auto_connect=False)
        try:
            scope.connect()
            instrument = getattr(scope, "scope", None)
            if instrument is not None:
                instrument.timeout = timeout_ms
                try:
                    instrument.write_termination = "\n"
                    instrument.read_termination = "\n"
                except Exception:
                    pass
            return callback(scope)
        finally:
            try:
                scope.disconnect()
            except Exception:
                pass

    def _finish_scope_action_error(self, description: str, exc: BaseException) -> None:
        self._connection_ok = False
        self._last_action = f"Failed: {description}"
        self.statusBar().showMessage(f"Failed: {description}")
        self._append_log(f"ERROR: {exc}")
        self._operation_active = False
        self._update_scope_control_enabled()
        self._update_status_strip()
        self._message(description, str(exc), error=True)
        return None

    def _finish_scope_action_success(self, description: str, result: object) -> object | None:
        self._connection_ok = True
        self._operation_active = False
        self._last_action = f"Done: {description}"
        self._update_acquisition_state_from_description(description)
        self.statusBar().showMessage(f"Done: {description}")
        if result is not None:
            self._append_log(str(result))
        self._update_scope_control_enabled()
        self._update_status_strip()
        return result


__all__ = [
    "CollapsibleCard",
    "CONNECTION_PAGE_INDEX",
    "CONTROL_PAGE_BUILDERS",
    "PREFERENCE_PAGE_INDEXES",
    "PREVIEW_CONTROL_GUTTER_QSS",
    "PREVIEW_CONTROL_GUTTER_WIDTH",
    "SETTINGS_PAGE_INDEX",
    "TRIGGER_PAGE_INDEX",
    "WINDOW_TITLE",
    "QtScopeWindow",
]
