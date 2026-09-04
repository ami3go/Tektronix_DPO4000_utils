"""Stable launched PySide6 window for the DPO4000 GUI.

This module is the public launch foundation for the desktop application. It keeps
the mature top-menu/collapsible-card UI and exposes one worker-backed scope-action
gateway so later reliability layers can retry the same serialized operation path
without adding another VISA implementation.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QEventLoop

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

    def _execute_scope_action_once(
        self,
        resource: str,
        timeout_ms: int,
        callback: Callable[[Any], object],
    ) -> WorkerResult:
        """Execute one action attempt through the established short-lived worker path."""
        worker = start_scope_worker(
            lambda: self._run_snapshot_scope_session(resource, timeout_ms, callback)
        )
        loop = QEventLoop(self)
        box: dict[str, WorkerResult | None] = {"result": None}

        def on_finished(result: object) -> None:
            box["result"] = result if isinstance(result, WorkerResult) else WorkerResult(value=result)
            loop.quit()

        worker.signals.finished.connect(on_finished)
        self._active_scope_worker = worker
        loop.exec()
        self._active_scope_worker = None
        result = box["result"]
        if result is None:
            return WorkerResult(error=RuntimeError("Scope worker finished without result."))
        return result

    def _run_action(self, description: str, callback: Callable[[Any], object]) -> object | None:
        """Run a scope action through the shared worker gateway and preserve return values."""
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

        result = self._execute_scope_action_once(resource, timeout_ms, callback)
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
