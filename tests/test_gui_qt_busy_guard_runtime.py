"""Keyboard shortcuts must not re-enter a scope operation that is still running.

Scope-action buttons are disabled for the duration of an operation, but QShortcut
objects are not, and _run_action waits in a nested QEventLoop that keeps delivering
shortcut events. _guarded_scope_call is the single chokepoint every scope-requiring
shortcut passes through, so the busy check lives there.
"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from dpo4000_utils.gui_qt.display_window import FILE_PAGE_INDEX  # noqa: E402
from dpo4000_utils.gui_qt.ui_polish_window import QtScopeWindow  # noqa: E402


def _app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([sys.executable, "busy-guard-test"])
    return app


def _fire_shortcut(window, sequence: str) -> None:
    """Activate an installed global shortcut the way a key press would."""
    for shortcut in window._shortcuts:
        if shortcut.key().toString() == sequence:
            shortcut.activated.emit()
            return
    raise AssertionError(f"shortcut {sequence!r} is not installed")


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(QtScopeWindow, "_message", lambda self, *args, **kwargs: None)

    app = _app()
    win = QtScopeWindow()
    win.show()
    app.processEvents()
    win._connection_ok = True
    win._update_scope_control_enabled()
    try:
        yield win
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_shortcuts_stay_enabled_during_an_operation(window):
    """Guard the premise: disabling buttons does not disable shortcuts."""
    window._operation_active = True
    window._update_scope_control_enabled()

    assert window._scope_controls, "expected registered scope-action buttons"
    assert not any(button.isEnabled() for button in window._scope_controls)
    assert all(shortcut.isEnabled() for shortcut in window._shortcuts)


def test_guarded_call_runs_when_idle(window):
    calls = []
    window._guarded_scope_call(lambda: calls.append("ran"), "Capture preview")
    assert calls == ["ran"]


def test_guarded_call_is_blocked_while_an_operation_is_active(window):
    window._operation_active = True
    calls = []
    window._guarded_scope_call(lambda: calls.append("ran"), "Capture preview")
    assert calls == []
    assert "already running" in window.statusBar().currentMessage()


def test_shortcut_cannot_reenter_run_action_during_an_operation(window, monkeypatch):
    """The real defence: fire F5 while _run_action is still in flight."""
    descriptions: list[str] = []

    def fake_run_action(self, description, callback):
        descriptions.append(description)
        self._operation_active = True
        self._update_scope_control_enabled()
        try:
            if len(descriptions) == 1:
                # Stand in for the nested event loop still delivering shortcuts.
                _fire_shortcut(self, "F5")
        finally:
            self._operation_active = False
            self._update_scope_control_enabled()
        return

    monkeypatch.setattr(QtScopeWindow, "_run_action", fake_run_action)

    _fire_shortcut(window, "F5")

    assert descriptions == ["Refreshing scope preview"], (
        f"shortcut re-entered _run_action while an operation was active: {descriptions}"
    )


def test_default_setup_button_is_registered_as_a_scope_control(window):
    """The v0.6.7 Default button was in neither callback set, so it was never disabled."""
    window._select_drawer_page(FILE_PAGE_INDEX)
    default_button = next(
        (b for b in window.findChildren(QtWidgets.QAbstractButton) if b.text() == "Default"),
        None,
    )
    assert default_button is not None, "Default button not found on the File page"
    assert default_button in window._scope_controls

    window._operation_active = True
    window._update_scope_control_enabled()
    assert not default_button.isEnabled()


@pytest.mark.parametrize("label", ("Default", "IDN"))
def test_still_enabled_buttons_cannot_re_enter_run_action(window, monkeypatch, label):
    """Catch-all: even a button that stays enabled must not start a second session."""
    window._select_drawer_page(FILE_PAGE_INDEX)
    descriptions: list[str] = []
    monkeypatch.setattr(
        QtScopeWindow,
        "_run_snapshot_scope_session",
        staticmethod(lambda *args, **kwargs: None),
    )
    monkeypatch.setattr(
        QtScopeWindow,
        "_selected_resource",
        lambda self: "TCPIP0::127.0.0.1::INSTR",
    )
    original = QtScopeWindow._run_action

    def spy(self, description, callback):
        descriptions.append(description)
        return original(self, description, callback)

    monkeypatch.setattr(QtScopeWindow, "_run_action", spy)

    window._operation_active = True
    button = next(b for b in window.findChildren(QtWidgets.QAbstractButton) if b.text() == label)
    button.setEnabled(True)  # force the pre-fix condition even once classified
    button.click()

    assert descriptions, f"{label} did not reach _run_action at all"
    assert window.statusBar().currentMessage().endswith("a scope operation is already running"), (
        f"{label} was not refused: {window.statusBar().currentMessage()!r}"
    )


def test_idle_shortcut_still_reaches_run_action(window, monkeypatch):
    """The guard must not block the normal case."""
    descriptions: list[str] = []
    monkeypatch.setattr(
        QtScopeWindow,
        "_run_action",
        lambda self, description, callback: descriptions.append(description),
    )

    _fire_shortcut(window, "F5")

    assert descriptions == ["Refreshing scope preview"]
