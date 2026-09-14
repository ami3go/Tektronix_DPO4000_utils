from __future__ import annotations

import os
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from dpo4000_utils.gui_qt.scope_worker import PersistentScopeSession  # noqa: E402


class _Instrument:
    timeout = 1_000
    read_termination = "\n"
    write_termination = "\n"


class _Scope:
    instances: list["_Scope"] = []

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
        self.instrument = _Instrument()
        self.disconnect_calls = 0
        _Scope.instances.append(self)

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        self.disconnect_calls += 1

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
        app = QtWidgets.QApplication([sys.executable, "r0-fault-latency"])
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
    assert predicate(), "timed out waiting for persistent scope completion"


def _shutdown(manager: PersistentScopeSession) -> None:
    done = []
    manager.shutdown_async(on_finished=done.append)
    _pump_until(lambda: bool(done) and not manager.is_running)
    assert done[0].error is None


@pytest.mark.parametrize("delay_s", (0.0, 0.010, 0.100, 0.500))
def test_fake_scope_io_delay_matrix_completes_without_expanding_delay(delay_s: float) -> None:
    """Exercise the regression-plan 0/10/100/500 ms deterministic slow-I/O matrix."""

    _app()
    manager = PersistentScopeSession(scope_factory=_Scope)
    results = []
    started = time.perf_counter()
    try:
        manager.submit(
            "USB0::FAKE::INSTR",
            2_000,
            lambda _scope: (time.sleep(delay_s), delay_s)[1],
            on_finished=results.append,
        )
        _pump_until(lambda: bool(results), timeout_s=2.0)
        elapsed = time.perf_counter() - started
    finally:
        _shutdown(manager)

    assert results[0].error is None
    assert results[0].value == delay_s
    assert elapsed >= max(0.0, delay_s - 0.005)
    # Broad shared-runner ceiling: catches accidental VISA-timeout-scale stalls
    # without treating normal CI scheduling jitter as a performance regression.
    assert elapsed < delay_s + 1.0


def test_transport_failure_invalidates_session_and_next_request_reconnects() -> None:
    _app()
    _Scope.instances.clear()
    manager = PersistentScopeSession(scope_factory=_Scope)
    results = []

    def fail_after_delay(_scope):
        time.sleep(0.010)
        raise ConnectionError("simulated transport loss")

    try:
        manager.submit(
            "USB0::FAKE::INSTR",
            2_000,
            fail_after_delay,
            on_finished=results.append,
        )
        _pump_until(lambda: len(results) == 1)
        assert isinstance(results[0].error, ConnectionError)

        manager.submit(
            "USB0::FAKE::INSTR",
            2_000,
            lambda scope: id(scope),
            on_finished=results.append,
        )
        _pump_until(lambda: len(results) == 2)
        assert results[1].error is None
    finally:
        _shutdown(manager)

    assert len(_Scope.instances) == 2
    assert all(scope.disconnect_calls == 1 for scope in _Scope.instances)
