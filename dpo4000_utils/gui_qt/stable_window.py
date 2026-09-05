"""Stable launched PySide6 window for the DPO4000 GUI.

This module is the public launch foundation for the desktop application. Scope
operations execute on a worker and complete through Qt callbacks; the GUI thread
never enters a nested event loop while waiting for instrument I/O.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Slot

from ..instrument import DPO4000Scope
from ..session import scope_session
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
    """Stable launched Qt window with asynchronous worker-thread scope actions."""

    def _run_action(
        self,
        description: str,
        callback: Callable[[Any], object],
        *,
        on_success: Callable[[object], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> None:
        """Queue one short-lived worker action and return immediately."""
        if getattr(self, "_operation_active", False):
            self.statusBar().showMessage(
                f"Scope busy; finish the current operation before: {description}"
            )
            return

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
            self._finish_scope_action_error(description, exc)
            if on_error is not None:
                on_error(exc)
            return

        self._active_scope_action_context = (description, on_success, on_error)
        worker = start_scope_worker(
            lambda: self._run_snapshot_scope_session(resource, timeout_ms, callback)
        )
        self._active_scope_worker = worker
        worker.signals.finished.connect(self._on_scope_worker_finished)

    @Slot(object)
    def _on_scope_worker_finished(self, result: object) -> None:
        """Complete a worker action on the GUI thread."""
        worker_result = result if isinstance(result, WorkerResult) else WorkerResult(value=result)
        context = getattr(self, "_active_scope_action_context", None)
        self._active_scope_worker = None
        self._active_scope_action_context = None
        if not isinstance(context, tuple) or len(context) != 3:
            self._operation_active = False
            self._update_scope_control_enabled()
            self._update_status_strip()
            return

        description, on_success, on_error = context
        if worker_result.error is not None:
            self._finish_scope_action_error(description, worker_result.error)
            if on_error is not None:
                on_error(worker_result.error)
            return

        value = self._finish_scope_action_success(description, worker_result.value)
        if on_success is not None:
            on_success(value)

    @staticmethod
    def _run_snapshot_scope_session(
        resource: str,
        timeout_ms: int,
        callback: Callable[[DPO4000Scope], object],
    ) -> object:
        """Open one driver-owned short-lived session from GUI-state snapshots."""
        with scope_session(resource, timeout_ms=timeout_ms) as scope:
            return callback(scope)

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
