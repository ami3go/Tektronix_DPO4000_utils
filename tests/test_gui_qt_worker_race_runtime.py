"""_run_action must return even when its worker finishes before the wait begins.

The worker used to be started before its finished signal was connected. A callback
that fails fast -- pyvisa missing, so connect() raises in microseconds -- completes
in that gap, the emission reaches nobody, and the nested QEventLoop blocks forever
with the GUI frozen and no way out.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402

from dpo4000_utils.gui_qt.scope_worker import WorkerResult, start_scope_worker  # noqa: E402
from dpo4000_utils.gui_qt.ui_polish_window import QtScopeWindow  # noqa: E402

POLL_MS = 25
DEADLINE_MS = 5_000


def _app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([sys.executable, "worker-race-test"])
    return app


def _run_until(loop: QEventLoop, is_done: Callable[[], bool]) -> bool:
    """Spin *loop* until *is_done* or the deadline, never leaving a live timer behind.

    Every timer is owned and stopped here on purpose: a QTimer that outlives the
    QEventLoop it would quit fires against freed memory and crashes the interpreter
    at shutdown.
    """
    guard = QTimer()
    elapsed = {"ms": 0}

    def tick() -> None:
        elapsed["ms"] += POLL_MS
        if is_done() or elapsed["ms"] >= DEADLINE_MS:
            loop.quit()

    guard.setInterval(POLL_MS)
    guard.timeout.connect(tick)
    guard.start()
    try:
        loop.exec()
    finally:
        guard.stop()
        guard.timeout.disconnect(tick)
    return is_done()


def test_start_scope_worker_delivers_a_result_connected_before_start():
    """The signal is connected inside start_scope_worker, so it cannot be missed."""
    app = _app()
    received: list[object] = []
    loop = QEventLoop()

    def on_finished(result: object) -> None:
        received.append(result)
        loop.quit()

    # Keep the worker referenced for the duration, exactly as _run_action does via
    # _active_scope_worker; a collected QRunnable may never run at all.
    worker = start_scope_worker(lambda: "done", on_finished=on_finished)

    try:
        assert _run_until(loop, lambda: bool(received)), (
            "finished signal was emitted before the caller could connect"
        )
        app.processEvents()
    finally:
        del worker

    assert isinstance(received[0], WorkerResult)
    assert received[0].value == "done"


def test_run_action_returns_when_the_session_fails_immediately(tmp_path, monkeypatch):
    """End to end: an instantly-failing scope session must not strand _run_action."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(QtScopeWindow, "_message", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(
        QtScopeWindow,
        "_selected_resource",
        lambda self: "TCPIP0::127.0.0.1::INSTR",
    )

    def fail_fast(resource, timeout_ms, callback):
        raise RuntimeError("PyVISA is not available")

    monkeypatch.setattr(QtScopeWindow, "_run_snapshot_scope_session", staticmethod(fail_fast))

    app = _app()
    window = QtScopeWindow()
    window.show()
    app.processEvents()
    try:
        result = window._run_action("Testing scope connection", lambda scope: None)
        # The point is that this line is reached at all: the failure is reported and
        # the window is left usable, instead of the GUI hanging in the nested loop.
        assert result is None
        assert window._operation_active is False
        assert "PyVISA is not available" in window.statusBar().currentMessage()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
