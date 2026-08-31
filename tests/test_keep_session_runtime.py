from __future__ import annotations

import os
import sys
import threading
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
        self.instrument = FakeInstrument()
        self.instrument.read_termination = read_termination
        self.instrument.write_termination = write_termination
        self.connected = False
        self.connect_calls = 0
        self.disconnect_calls = 0
        FakeScope.instances.append(self)

    def connect(self) -> None:
        self.connected = True
        self.connect_calls += 1

    def disconnect(self) -> None:
        self.connected = False
        self.disconnect_calls += 1

    def ensure_connected(self):
        if not self.connected:
            raise ConnectionError("fake scope is not connected")
        return self.instrument


def _app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([sys.executable, "persistent-scope-test"])
    return app


def test_persistent_scope_session_reuses_one_scope_on_one_worker_thread():
    _app()
    FakeScope.instances.clear()
    manager = PersistentScopeSession(scope_factory=FakeScope)
    main_thread = threading.get_ident()
    try:
        first = manager.execute("USB0::FAKE::INSTR", 20_000, lambda _scope: threading.get_ident())
        second = manager.execute("USB0::FAKE::INSTR", 25_000, lambda _scope: threading.get_ident())

        assert first.error is None
        assert second.error is None
        assert first.value == second.value
        assert first.value != main_thread
        assert len(FakeScope.instances) == 1
        scope = FakeScope.instances[0]
        assert scope.connect_calls == 1
        assert scope.disconnect_calls == 0
        assert scope.instrument.timeout == 25_000

        closed = manager.close_scope()
        assert closed.error is None
        assert scope.disconnect_calls == 1
    finally:
        manager.shutdown()


def test_non_transport_error_keeps_persistent_session_alive():
    _app()
    FakeScope.instances.clear()
    manager = PersistentScopeSession(scope_factory=FakeScope)

    def invalid_operation(_scope):
        raise ValueError("invalid setting")

    try:
        failed = manager.execute("USB0::FAKE::INSTR", 20_000, invalid_operation)
        assert isinstance(failed.error, ValueError)
        assert len(FakeScope.instances) == 1
        first_scope = FakeScope.instances[0]
        assert first_scope.disconnect_calls == 0

        follow_up = manager.execute("USB0::FAKE::INSTR", 20_000, lambda scope: id(scope))
        assert follow_up.error is None
        assert follow_up.value == id(first_scope)
        assert len(FakeScope.instances) == 1
    finally:
        manager.shutdown()


def test_transport_error_invalidates_persistent_session_and_next_action_reconnects():
    _app()
    FakeScope.instances.clear()
    manager = PersistentScopeSession(scope_factory=FakeScope)

    def transport_failure(_scope):
        raise ConnectionError("link lost")

    try:
        failed = manager.execute("USB0::FAKE::INSTR", 20_000, transport_failure)
        assert isinstance(failed.error, ConnectionError)
        assert len(FakeScope.instances) == 1
        assert FakeScope.instances[0].disconnect_calls == 1

        recovered = manager.execute("USB0::FAKE::INSTR", 20_000, lambda scope: id(scope))
        assert recovered.error is None
        assert len(FakeScope.instances) == 2
        assert recovered.value == id(FakeScope.instances[1])
        assert FakeScope.instances[1].connect_calls == 1
    finally:
        manager.shutdown()


def test_keep_session_checkbox_defaults_off_and_persists_when_enabled(tmp_path):
    app = _app()
    preferences_path = tmp_path / "gui_preferences.json"
    window = QtScopeWindow(preferences_path=preferences_path)
    try:
        assert window.keep_session.text() == "Keep session"
        assert window.keep_session.isChecked() is False
        window.keep_session.setChecked(True)
        assert window._collect_preferences().keep_session is True
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()

    assert load_preferences(preferences_path).keep_session is True


def test_unchecked_keep_session_preserves_existing_per_operation_fallback():
    source = Path("dpo4000_utils/gui_qt/preview_actions_window.py").read_text(encoding="utf-8")

    assert 'QCheckBox("Keep session")' in source
    assert "if keep_session is None or not keep_session.isChecked():" in source
    assert "return super()._run_action(description, callback)" in source
