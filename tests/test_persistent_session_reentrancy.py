"""PersistentScopeSession must never hand a caller another request's result.

_wait_for waits on a nested QEventLoop, which keeps dispatching GUI events, so a
second call can arrive before the first has finished. Each call connects its own
finished handler and the earlier one is still connected, so a single completion
wakes both and the inner caller returns with the outer request's value.
"""

from __future__ import annotations

import os
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QTimer  # noqa: E402

from dpo4000_utils.gui_qt.scope_worker import PersistentScopeSession  # noqa: E402


RESOURCE = "TCPIP0::127.0.0.1::INSTR"


class FakeInstrument:
    timeout = 0
    write_termination = ""
    read_termination = ""


class FakeScope:
    """Minimal stand-in for DPO4054; no VISA involved."""

    def __init__(self, *args, **kwargs) -> None:
        self.connected = False

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def ensure_connected(self) -> FakeInstrument:
        return FakeInstrument()


def _app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([sys.executable, "persistent-reentrancy-test"])
    return app


@pytest.fixture
def session():
    _app()
    manager = PersistentScopeSession(scope_factory=lambda *a, **k: FakeScope())
    try:
        yield manager
    finally:
        manager.shutdown()


def test_sequential_calls_each_get_their_own_result(session):
    for index in range(5):
        result = session.execute(RESOURCE, 1000, lambda scope, i=index: f"value-{i}")
        assert result.error is None
        assert result.value == f"value-{index}"


def test_reentrant_call_is_refused_instead_of_getting_the_wrong_result(session):
    inner: list = []

    def reenter() -> None:
        inner.append(session.execute(RESOURCE, 1000, lambda scope: "INNER"))

    # Fires while the outer request is still being waited on.
    QTimer.singleShot(50, reenter)

    def slow(scope) -> str:
        time.sleep(0.4)
        return "OUTER"

    outer = session.execute(RESOURCE, 1000, slow)
    _app().processEvents()

    assert outer.error is None
    assert outer.value == "OUTER", "the outer caller must still get its own result"

    assert inner, "the re-entrant call never returned"
    assert inner[0].value != "OUTER", "inner call was handed the outer request's result"
    assert inner[0].error is not None
    assert "cannot be re-entered" in str(inner[0].error)


def test_session_is_usable_again_after_a_refused_reentrant_call(session):
    inner: list = []
    QTimer.singleShot(50, lambda: inner.append(session.execute(RESOURCE, 1000, lambda s: "INNER")))
    session.execute(RESOURCE, 1000, lambda scope: time.sleep(0.4) or "OUTER")
    _app().processEvents()
    assert inner and inner[0].error is not None

    after = session.execute(RESOURCE, 1000, lambda scope: "AFTER")
    assert after.error is None
    assert after.value == "AFTER"


def test_repeated_fast_requests_do_not_strand_the_wait(session):
    """Smoke test for the lost-wakeup shape: the handler runs on the worker thread."""
    for index in range(200):
        result = session.execute(RESOURCE, 1000, lambda scope, i=index: i)
        assert result.error is None, f"iteration {index} failed: {result.error}"
        assert result.value == index
