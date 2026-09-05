from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtCore = pytest.importorskip("PySide6.QtCore")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from dpo4000_utils.gui.preferences import load_preferences  # noqa: E402
from dpo4000_utils.gui_qt.preview_actions_window import QtScopeWindow  # noqa: E402
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
        self.connected = False
        self.connect_calls = 0
        self.disconnect_calls = 0
        FakeScope.instances.append(self)

    def connect(self) -> None:
        self.connected = True
        self.connect_calls += 1
        self.configure_session(
            timeout_ms=self.timeout_ms,
            read_termination=self.read_termination,
            write_termination=self.write_termination,
        )

    def disconnect(self) -> None:
        self.connected = False
        self.disconnect_calls += 1

    def configure_session(
        self,
        *,
        timeout_ms: int | None = None,
        read_termination: str | None = None,
        write_termination: str | None = None,
    ):
        if timeout_ms is not None:
            self.timeout_ms = int(timeout_ms)
            self.instrument.timeout = int(timeout_ms)
        if read_termination is not None:
            self.read_termination = read_termination
            self.instrument.read_termination = read_termination
        if write_termination is not None:
            self.write_termination = write_termination
            self.instrument.write_termination = write_termination
        return {
            "timeout_ms": self.timeout_ms,
            "read_termination": self.read_termination,
            "write_termination": self.write_termination,
        }


def _app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([sys.executable, "persistent-scope-test"])
    return app


def _wait_until(predicate, *, timeout_s: float = 3.0) -> None:
    app = _app()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    app.processEvents()
    assert predicate(), "timed out waiting for asynchronous Qt completion"


def _submit_and_wait(manager: PersistentScopeSession, resource, timeout_ms, callback):
    results = []
    request_id = manager.submit(
        resource,
        timeout_ms,
        callback,
        on_finished=results.append,
    )
    _wait_until(lambda: bool(results))
    return request_id, results[0]


def _shutdown_and_wait(manager: PersistentScopeSession):
    results = []
    manager.shutdown_async(on_finished=results.append)
    _wait_until(lambda: bool(results) and not manager.is_running)
    return results[0]


def test_persistent_scope_session_reuses_one_scope_on_one_worker_thread():
    _app()
    FakeScope.instances.clear()
    manager = PersistentScopeSession(scope_factory=FakeScope)
    main_thread = threading.get_ident()
    try:
        _, first = _submit_and_wait(
            manager,
            "USB0::FAKE::INSTR",
            20_000,
            lambda _scope: threading.get_ident(),
        )
        _, second = _submit_and_wait(
            manager,
            "USB0::FAKE::INSTR",
            25_000,
            lambda _scope: threading.get_ident(),
        )

        assert first.error is None
        assert second.error is None
        assert first.value == second.value
        assert first.value != main_thread
        assert len(FakeScope.instances) == 1
        scope = FakeScope.instances[0]
        assert scope.connect_calls == 1
        assert scope.disconnect_calls == 0
        assert scope.instrument.timeout == 25_000

        closed = []
        manager.close_scope_async(on_finished=closed.append)
        _wait_until(lambda: bool(closed))
        assert closed[0].error is None
        assert scope.disconnect_calls == 1
    finally:
        _shutdown_and_wait(manager)


def test_non_transport_error_keeps_persistent_session_alive():
    _app()
    FakeScope.instances.clear()
    manager = PersistentScopeSession(scope_factory=FakeScope)

    def invalid_operation(_scope):
        raise ValueError("invalid setting")

    try:
        _, failed = _submit_and_wait(
            manager,
            "USB0::FAKE::INSTR",
            20_000,
            invalid_operation,
        )
        assert isinstance(failed.error, ValueError)
        assert len(FakeScope.instances) == 1
        first_scope = FakeScope.instances[0]
        assert first_scope.disconnect_calls == 0

        _, follow_up = _submit_and_wait(
            manager,
            "USB0::FAKE::INSTR",
            20_000,
            lambda scope: id(scope),
        )
        assert follow_up.error is None
        assert follow_up.value == id(first_scope)
        assert len(FakeScope.instances) == 1
    finally:
        _shutdown_and_wait(manager)


def test_transport_error_invalidates_persistent_session_and_next_action_reconnects():
    _app()
    FakeScope.instances.clear()
    manager = PersistentScopeSession(scope_factory=FakeScope)

    def transport_failure(_scope):
        raise ConnectionError("link lost")

    try:
        _, failed = _submit_and_wait(
            manager,
            "USB0::FAKE::INSTR",
            20_000,
            transport_failure,
        )
        assert isinstance(failed.error, ConnectionError)
        assert len(FakeScope.instances) == 1
        assert FakeScope.instances[0].disconnect_calls == 1

        _, recovered = _submit_and_wait(
            manager,
            "USB0::FAKE::INSTR",
            20_000,
            lambda scope: id(scope),
        )
        assert recovered.error is None
        assert len(FakeScope.instances) == 2
        assert recovered.value == id(FakeScope.instances[1])
        assert FakeScope.instances[1].connect_calls == 1
    finally:
        _shutdown_and_wait(manager)


def test_cancelled_queued_request_does_not_execute_callback():
    _app()
    FakeScope.instances.clear()
    manager = PersistentScopeSession(scope_factory=FakeScope)
    gate = threading.Event()
    ran_cancelled_callback = threading.Event()
    first_results = []
    second_results = []
    try:
        manager.submit(
            "USB0::FAKE::INSTR",
            20_000,
            lambda _scope: gate.wait(0.5),
            on_finished=first_results.append,
        )
        second_id = manager.submit(
            "USB0::FAKE::INSTR",
            20_000,
            lambda _scope: ran_cancelled_callback.set(),
            on_finished=second_results.append,
        )
        assert manager.cancel(second_id)
        gate.set()
        _wait_until(lambda: bool(first_results) and bool(second_results))
        assert second_results[0].cancelled is True
        assert not ran_cancelled_callback.is_set()
    finally:
        _shutdown_and_wait(manager)


def test_keep_session_defaults_on_and_persists_when_disabled(tmp_path):
    app = _app()
    preferences_path = tmp_path / "gui_preferences.json"
    window = QtScopeWindow(preferences_path=preferences_path)
    try:
        assert window.keep_session.text() == "Keep session"
        assert window.keep_session.isChecked() is True
        window.keep_session.setChecked(False)
        assert window._collect_preferences().keep_session is False
    finally:
        window.close()
        _wait_until(lambda: window._scope_shutdown_complete)
        window.deleteLater()
        app.processEvents()

    assert load_preferences(preferences_path).keep_session is False


def test_production_scope_runtime_has_no_nested_qeventloop():
    worker_source = Path("dpo4000_utils/gui_qt/scope_worker.py").read_text(encoding="utf-8")
    stable_source = Path("dpo4000_utils/gui_qt/stable_window.py").read_text(encoding="utf-8")
    preview_source = Path("dpo4000_utils/gui_qt/preview_actions_window.py").read_text(
        encoding="utf-8"
    )

    assert "QEventLoop" not in worker_source
    assert "QEventLoop" not in stable_source
    assert "QEventLoop" not in preview_source
    assert "manager.submit(" in preview_source
    assert "shutdown_async(" in preview_source
