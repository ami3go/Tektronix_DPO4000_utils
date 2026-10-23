from __future__ import annotations

import os
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from dpo4000_utils.gui_qt.scope_worker import PersistentScopeSession  # noqa: E402


class _FakeInstrument:
    def __init__(self) -> None:
        self.timeout = 1_000
        self.read_termination = "\n"
        self.write_termination = "\n"


class _FakeScope:
    instances: list["_FakeScope"] = []

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
        self.disconnect_calls = 0
        _FakeScope.instances.append(self)

    def connect(self) -> None:
        self.configure_session(
            timeout_ms=self.timeout_ms,
            read_termination=self.read_termination,
            write_termination=self.write_termination,
        )

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
        app = QtWidgets.QApplication([sys.executable, "r0-fake-io-latency"])
    return app


def _wait_until(predicate, *, timeout_s: float = 3.0) -> None:
    app = _app()
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.001)
    app.processEvents()
    assert predicate(), "timed out waiting for fake-I/O regression completion"


def _shutdown(manager: PersistentScopeSession) -> None:
    completions = []
    manager.shutdown_async(on_finished=completions.append)
    _wait_until(lambda: bool(completions) and not manager.is_running)
    assert completions[0].error is None


@pytest.mark.parametrize("delay_s", (0.0, 0.010, 0.100, 0.500))
def test_fake_io_latency_matrix_preserves_async_completion(delay_s: float) -> None:
    _app()
    _FakeScope.instances.clear()
    manager = PersistentScopeSession(scope_factory=_FakeScope)
    results = []

    try:
        started = time.perf_counter()

        def operation(_scope):
            time.sleep(delay_s)
            return delay_s

        manager.submit(
            "USB0::FAKE::INSTR",
            2_000,
            operation,
            on_finished=results.append,
        )
        _wait_until(lambda: bool(results), timeout_s=max(2.0, delay_s + 1.0))
        elapsed = time.perf_counter() - started

        assert results[0].error is None
        assert results[0].value == delay_s
        assert elapsed >= delay_s * 0.90
        assert elapsed < delay_s + 1.0
    finally:
        _shutdown(manager)


@pytest.mark.parametrize("delay_s", (0.0, 0.010, 0.100, 0.500))
def test_fake_transport_failure_matrix_closes_session_and_recovers(delay_s: float) -> None:
    _app()
    _FakeScope.instances.clear()
    manager = PersistentScopeSession(scope_factory=_FakeScope)
    results = []

    try:
        def fail(_scope):
            time.sleep(delay_s)
            raise ConnectionError(f"simulated link loss after {delay_s:.3f}s")

        manager.submit(
            "USB0::FAKE::INSTR",
            2_000,
            fail,
            on_finished=results.append,
        )
        _wait_until(lambda: len(results) == 1, timeout_s=max(2.0, delay_s + 1.0))
        assert isinstance(results[0].error, ConnectionError)
        assert len(_FakeScope.instances) == 1
        assert _FakeScope.instances[0].disconnect_calls == 1

        manager.submit(
            "USB0::FAKE::INSTR",
            2_000,
            lambda _scope: "recovered",
            on_finished=results.append,
        )
        _wait_until(lambda: len(results) == 2)
        assert results[1].error is None
        assert results[1].value == "recovered"
        assert len(_FakeScope.instances) == 2
    finally:
        _shutdown(manager)

    assert all(scope.disconnect_calls == 1 for scope in _FakeScope.instances)
