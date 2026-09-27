from __future__ import annotations

import os
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtCore = pytest.importorskip("PySide6.QtCore")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from dpo4000_utils.gui_qt.scope_worker import PersistentScopeSession  # noqa: E402
from dpo4000_utils.regression import summarize_timings  # noqa: E402


class _FakeInstrument:
    timeout = 1_000
    read_termination = "\n"
    write_termination = "\n"


class _SlowScope:
    def __init__(
        self,
        resource: str,
        *,
        auto_connect: bool = False,
        timeout_ms: int | None = None,
        read_termination: str | None = "\n",
        write_termination: str | None = "\n",
    ) -> None:
        self.resource = resource
        self.timeout_ms = timeout_ms
        self.read_termination = read_termination
        self.write_termination = write_termination
        self.instrument = _FakeInstrument()

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def configure_session(
        self,
        *,
        timeout_ms: int | None = None,
        read_termination: str | None = None,
        write_termination: str | None = None,
    ) -> None:
        if timeout_ms is not None:
            self.instrument.timeout = int(timeout_ms)
        if read_termination is not None:
            self.instrument.read_termination = read_termination
        if write_termination is not None:
            self.instrument.write_termination = write_termination


def _app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([sys.executable, "r0-gui-heartbeat"])
    return app


def _pump_until(predicate, *, timeout_s: float = 3.0) -> None:
    app = _app()
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.001)
    app.processEvents()
    assert predicate(), "timed out while pumping the GUI event loop"


def _shutdown(manager: PersistentScopeSession) -> None:
    completions = []
    manager.shutdown_async(on_finished=completions.append)
    _pump_until(lambda: bool(completions) and not manager.is_running)
    assert completions[0].error is None


def test_gui_heartbeat_remains_alive_during_slow_scope_io() -> None:
    """A blocking 350 ms instrument operation must remain off the GUI thread."""

    _app()
    manager = PersistentScopeSession(scope_factory=_SlowScope)
    ticks: list[float] = []
    completed_at: list[float] = []
    result = []
    timer = QtCore.QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.append(time.perf_counter()))
    timer.start()

    try:
        started = time.perf_counter()

        def slow_operation(_scope):
            time.sleep(0.350)
            return "done"

        def finished(worker_result) -> None:
            completed_at.append(time.perf_counter())
            result.append(worker_result)

        manager.submit(
            "USB0::FAKE::INSTR",
            2_000,
            slow_operation,
            on_finished=finished,
        )
        _pump_until(lambda: bool(result), timeout_s=2.0)
    finally:
        timer.stop()
        _shutdown(manager)

    assert result[0].error is None
    assert result[0].value == "done"
    assert completed_at
    active_ticks = [tick for tick in ticks if started <= tick <= completed_at[0]]
    assert len(active_ticks) >= 5, "GUI heartbeat stopped while worker performed blocking I/O"

    gaps = [later - earlier for earlier, later in zip(active_ticks, active_ticks[1:])]
    if gaps:
        summary = summarize_timings(gaps)
        # This is a deliberately broad shared-CI ceiling. If the 350 ms operation
        # accidentally moves to the GUI thread the heartbeat gap approaches the
        # entire operation duration and fails decisively.
        assert summary.maximum < 0.250
