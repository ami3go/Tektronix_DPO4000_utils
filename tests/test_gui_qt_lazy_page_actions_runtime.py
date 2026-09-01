"""Quick actions must work on a freshly launched window.

Control pages are built lazily, so an action that reads a widget owned by a page
the user has not visited yet raised AttributeError inside the Qt slot. Qt swallows
that exception, so the button silently did nothing. These tests drive the real
buttons and shortcut handlers with no page navigation at all.
"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from dpo4000_utils.gui_qt.ui_polish_window import QtScopeWindow  # noqa: E402

QUICK_ACTIONS = ("IDN", "Preview", "Copy", "Image", "CSV", "Run", "Stop", "Single", "Force")
SHORTCUT_HANDLERS = (
    "capture_preview",
    "save_png_image",
    "save_csv",
    "run_acquisition",
    "stop_acquisition",
    "single_acquisition",
)


def _app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([sys.executable, "lazy-page-actions-test"])
    return app


@pytest.fixture
def slot_errors(monkeypatch):
    """Collect exceptions Qt swallows when they escape a slot.

    A button click routes through C++, so an exception raised in the connected
    handler never propagates to the caller; Qt reports it through sys.excepthook
    and carries on. Without this the click tests would pass against the very bug
    they exist to catch.
    """
    captured: list[BaseException] = []
    monkeypatch.setattr(sys, "excepthook", lambda kind, value, tb: captured.append(value))
    return captured


@pytest.fixture
def window(tmp_path, monkeypatch, slot_errors):
    """A shown window with the scope unlocked and all instrument I/O stubbed out."""
    monkeypatch.chdir(tmp_path)  # contain the output folder actions create
    monkeypatch.setattr(QtScopeWindow, "_run_action", lambda self, description, callback: None)
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


def test_only_the_default_page_is_built_at_startup(window):
    """Guard the premise: the pages these actions depend on really are unbuilt."""
    assert window._lazy_control_pages_built[0] is True
    assert not any(window._lazy_control_pages_built[1:])
    assert not hasattr(window, "rearm_after_image")
    assert not hasattr(window, "png_prefix")


@pytest.mark.parametrize("label", QUICK_ACTIONS)
def test_quick_action_button_click_does_not_raise(window, slot_errors, label):
    button = next(
        (item for item in window.findChildren(QtWidgets.QAbstractButton) if item.text() == label),
        None,
    )
    assert button is not None, f"quick action {label!r} not found"
    button.click()
    assert not slot_errors, f"{label!r} raised {slot_errors[0]!r} inside its Qt slot"


@pytest.mark.parametrize("method_name", SHORTCUT_HANDLERS)
def test_keyboard_shortcut_handler_does_not_raise(window, method_name):
    getattr(window, method_name)()


def test_preview_builds_the_trigger_page_on_demand(window):
    """capture_preview reads rearm_after_image, which _build_trigger_tab owns."""
    window.capture_preview()
    assert hasattr(window, "rearm_after_image")
    assert hasattr(window, "trigger_channel_after_image")


def test_save_png_image_builds_the_file_page_on_demand(window):
    """save_png_image builds an output path from widgets _build_file_tab owns."""
    window.save_png_image()
    assert hasattr(window, "png_prefix")
    assert hasattr(window, "output_folder")


def test_accessors_build_their_own_page(window):
    """The guard lives on the accessor so a later override cannot drop it."""
    assert isinstance(window._rearm_after_image_enabled(), bool)
    assert window._trigger_channel_or_none() is None or isinstance(
        window._trigger_channel_or_none(), int
    )
    assert window._build_output_path("png").suffix == ".png"
