"""Shared Qt fixtures.

Building a window was awkward enough that much of the GUI suite asserted on source
text instead, which is why a formatting-only change could break tests and a real
crash could pass them. These fixtures make the behavioural version the easy one.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Fixtures below chdir into a tmp dir, so repo files must be reached absolutely.
REPO_ROOT = Path(__file__).resolve().parents[1]

# Imported once here rather than per helper. conftest is loaded for the whole suite,
# including the tests that need no Qt, so a missing PySide6 must not skip everything.
try:
    from PySide6 import QtWidgets
except ModuleNotFoundError:  # pragma: no cover - exercised only without the extra.
    QtWidgets = None


@pytest.fixture(scope="session")
def qt_app():
    """One QApplication for the whole session; Qt does not support more."""
    if QtWidgets is None:
        pytest.skip("PySide6 is not installed")
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([sys.executable, "dpo4000-tests"])
    return app


@pytest.fixture
def make_window(qt_app, tmp_path, monkeypatch):
    """Build a launched window with instrument I/O stubbed and output contained.

    Yields a factory so a test can opt into a different class or into running the
    real ``_run_action``. Windows are closed for you.
    """
    monkeypatch.chdir(tmp_path)
    created = []

    def factory(window_class=None, *, stub_actions=True, show=True):
        if window_class is None:
            from dpo4000_utils.gui_qt import ui_polish_window

            window_class = ui_polish_window.QtScopeWindow
        if stub_actions:
            monkeypatch.setattr(
                window_class, "_run_action", lambda self, description, callback: None, raising=False
            )
        monkeypatch.setattr(
            window_class, "_message", lambda self, *args, **kwargs: None, raising=False
        )
        window = window_class()
        created.append(window)
        if show:
            window.show()
        qt_app.processEvents()
        return window

    try:
        yield factory
    finally:
        for window in created:
            window.close()
            window.deleteLater()
        qt_app.processEvents()


@pytest.fixture
def unlocked_window(make_window):
    """A shown window with scope controls unlocked, as after a successful IDN test."""
    window = make_window()
    window._connection_ok = True
    window._update_scope_control_enabled()
    return window


def button_named(window, text: str):
    """Return the first button whose visible label is *text*, or None."""
    return next(
        (b for b in window.findChildren(QtWidgets.QAbstractButton) if b.text() == text), None
    )


def button_texts(window) -> set[str]:
    return {b.text() for b in window.findChildren(QtWidgets.QAbstractButton)}


def card_titles(window) -> set[str]:
    """Titles of the cards on the current page.

    Plain QGroupBox cards are rewrapped as CollapsibleCard, which moves the title
    out of the group box and into its clickable header, so looking only at
    QGroupBox.title() finds nothing but empty strings.
    """
    from dpo4000_utils.gui_qt.collapsible_window import CollapsibleCard

    titles = {card._base_title for card in window.findChildren(CollapsibleCard)}
    titles |= {g.title() for g in window.findChildren(QtWidgets.QGroupBox) if g.title()}
    return titles
