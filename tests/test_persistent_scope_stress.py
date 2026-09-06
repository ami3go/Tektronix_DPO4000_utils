from __future__ import annotations

import os
import sys
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from dpo4000_utils.gui_qt.scope_worker import PersistentScopeSession  # noqa: E402


class FakeInstrument:
    def __init__(self) -> None:
        self.timeout = 1_000
        self.read_termination = "\n"
        self.write_termination = "\n"


class FakeScope:
    instances: list["FakeScope"] = []

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
        self.auto_connect = auto_connect
        self.timeout_ms = timeout_ms
        self.read_termination = read_termination
        self.write_termination = write_termination
        self.instrument = FakeInstrument()
        self.connect_calls = 0
        self.disconnect_calls = 0
        FakeScope.instances.append(self)

    def connect(self) -> None:
        self.connect_calls += 1
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
            self.timeout_ms = int(timeout_ms)
            self.instrument.timeout = int(timeout_ms)
        if read_termination is not None:
            self.read_termination = read_termination
            self.instrument.read_termination = read_termination
        if write_termination is not None:
            self.write_termination = write_termination
            self.instrument.write_termination = write_termination


def _app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([sys.executable, "persistent-scope-stress"])
    return app


def _wait_until(predicate, *, timeout_s: float = 10.0) -> None:
    app = _app()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.001)
    app.processEvents()
    assert predicate(), "timed out waiting for asynchronous stress-test completion"


def _shutdown(manager: PersistentScopeSession) -> None:
    completions = []
    manager.shutdown_async(on_finished=completions.append)
    _wait_until(lambda: bool(completions) and not manager.is_running)
    assert completions[0].error is None
    assert not manager.has_pending_requests


def test_persistent_scope_reuses_one_session_for_thousand_requests() -> None:
    _app()
    FakeScope.instances.clear()
    manager = PersistentScopeSession(scope_factory=FakeScope)
    results = []
    try:
        for sequence in range(1_000):
            timeout_ms = 2_000 + sequence % 17
            manager.submit(
                "USB0::FAKE::INSTR",
                timeout_ms,
                lambda scope, sequence=sequence: (
                    id(scope),
                    threading.get_ident(),
                    sequence,
                ),
                on_finished=results.append,
            )

        _wait_until(lambda: len(results) == 1_000)
        assert all(result.error is None and not result.cancelled for result in results)
        values = [result.value for result in results]
        assert [value[2] for value in values] == list(range(1_000))
        assert len({value[0] for value in values}) == 1
        assert len({value[1] for value in values}) == 1
        assert len(FakeScope.instances) == 1
        scope = FakeScope.instances[0]
        assert scope.connect_calls == 1
        assert scope.disconnect_calls == 0
        assert scope.instrument.timeout == 2_000 + 999 % 17
    finally:
        _shutdown(manager)

    assert FakeScope.instances[0].disconnect_calls == 1


def test_transport_failures_reconnect_without_accumulating_live_sessions() -> None:
    _app()
    FakeScope.instances.clear()
    manager = PersistentScopeSession(scope_factory=FakeScope)
    results = []
    failure_indexes = {39, 79, 119, 159, 199}

    def operation(scope, index: int):
        if index in failure_indexes:
            raise ConnectionError(f"simulated link loss at {index}")
        return id(scope), index

    try:
        for index in range(240):
            manager.submit(
                "USB0::FAKE::INSTR",
                5_000,
                lambda scope, index=index: operation(scope, index),
                on_finished=results.append,
            )

        _wait_until(lambda: len(results) == 240)
        failures = [result for result in results if result.error is not None]
        successes = [result for result in results if result.error is None]
        assert len(failures) == len(failure_indexes)
        assert all(isinstance(result.error, ConnectionError) for result in failures)
        assert len(successes) == 240 - len(failure_indexes)
        assert len(FakeScope.instances) == len(failure_indexes) + 1
        assert all(scope.disconnect_calls == 1 for scope in FakeScope.instances[:-1])
        assert FakeScope.instances[-1].disconnect_calls == 0
    finally:
        _shutdown(manager)

    assert all(scope.disconnect_calls == 1 for scope in FakeScope.instances)


def test_cancelled_queue_stress_never_runs_cancelled_callbacks() -> None:
    _app()
    FakeScope.instances.clear()
    manager = PersistentScopeSession(scope_factory=FakeScope)
    gate = threading.Event()
    results = []
    ran: list[int] = []

    try:
        manager.submit(
            "USB0::FAKE::INSTR",
            5_000,
            lambda _scope: gate.wait(2.0),
            on_finished=results.append,
        )

        request_ids: list[tuple[int, int]] = []
        for index in range(100):
            request_id = manager.submit(
                "USB0::FAKE::INSTR",
                5_000,
                lambda _scope, index=index: ran.append(index),
                on_finished=results.append,
            )
            request_ids.append((request_id, index))

        cancelled_indexes = {
            index
            for request_id, index in request_ids
            if index % 2 == 0 and manager.cancel(request_id)
        }
        assert cancelled_indexes == set(range(0, 100, 2))
        gate.set()

        _wait_until(lambda: len(results) == 101)
        assert sum(result.cancelled for result in results) == 50
        assert sorted(ran) == list(range(1, 100, 2))
    finally:
        gate.set()
        _shutdown(manager)


def test_repeated_session_start_shutdown_cycles_close_every_scope() -> None:
    _app()
    FakeScope.instances.clear()

    for cycle in range(20):
        manager = PersistentScopeSession(scope_factory=FakeScope)
        results = []
        manager.submit(
            f"USB0::FAKE::{cycle}::INSTR",
            3_000,
            lambda scope: id(scope),
            on_finished=results.append,
        )
        _wait_until(lambda: bool(results))
        assert results[0].error is None
        _shutdown(manager)

    assert len(FakeScope.instances) == 20
    assert all(scope.connect_calls == 1 for scope in FakeScope.instances)
    assert all(scope.disconnect_calls == 1 for scope in FakeScope.instances)
