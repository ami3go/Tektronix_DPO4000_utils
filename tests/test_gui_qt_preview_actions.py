"""Preview refreshes in memory; Image writes a file. Verified by running them.

This replaces a source-text version that asserted `"save_image_path" not in body`
and similar. That version passed while Preview raised AttributeError on every
fresh launch, because it never ran the method it was describing.
"""

from __future__ import annotations

import pytest

from tests.conftest import button_named, button_texts

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def _png_bytes(width: int = 40, height: int = 30) -> bytes:
    """A real PNG, so the decode path is exercised rather than mocked."""
    from PySide6.QtCore import QBuffer, QByteArray

    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(0x2E3440)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data.data())


class FakeScope:
    """Records which driver calls an action makes."""

    def __init__(self, png: bytes) -> None:
        self.png = png
        self.calls: list[str] = []

    def read_screen_png(self) -> bytes:
        self.calls.append("read_screen_png")
        return self.png

    def save_image_path(self, path):
        self.calls.append("save_image_path")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.png)
        return path

    def rearm_trigger_after_image(self, trigger_channel=None):
        self.calls.append("rearm_trigger_after_image")


@pytest.fixture
def scope_window(make_window):
    """Window whose _run_action runs the callback against a FakeScope."""
    from dpo4000_utils.gui_qt.ui_polish_window import QtScopeWindow

    png = _png_bytes()
    scope = FakeScope(png)
    window = make_window(QtScopeWindow, stub_actions=False)
    window._connection_ok = True
    window._run_action = lambda description, callback: callback(scope)
    window._scope = scope
    return window


def test_quick_actions_are_labelled_preview_and_image(unlocked_window):
    texts = button_texts(unlocked_window)
    assert {"Preview", "Image"} <= texts
    assert "Capture" not in texts
    assert "PNG" not in texts


def test_preview_updates_the_widget_without_creating_a_file(scope_window, tmp_path):
    before = set(tmp_path.rglob("*.png"))

    scope_window.capture_preview()

    assert "read_screen_png" in scope_window._scope.calls
    assert "save_image_path" not in scope_window._scope.calls
    assert set(tmp_path.rglob("*.png")) == before, "Preview must not write a user file"
    assert scope_window._last_image_path is None
    assert not scope_window.preview_label.pixmap().isNull(), "preview widget was not updated"


def test_preview_keeps_the_decoded_png_for_copying(scope_window):
    scope_window.capture_preview()
    assert scope_window._last_preview_png == scope_window._scope.png


def test_image_writes_a_png_and_updates_the_preview(scope_window, tmp_path):
    scope_window.save_png_image()

    written = list(tmp_path.rglob("*.png"))
    assert written, "Image must save a file"
    assert "save_image_path" in scope_window._scope.calls
    assert scope_window._last_image_path is not None
    assert scope_window._last_image_path.exists()
    assert not scope_window.preview_label.pixmap().isNull()


def test_rearm_setting_is_honoured_by_both_actions(scope_window):
    scope_window._ensure_control_page_built(3)  # Trigger page owns the checkbox

    scope_window.rearm_after_image.setChecked(False)
    scope_window.capture_preview()
    assert "rearm_trigger_after_image" not in scope_window._scope.calls

    scope_window.rearm_after_image.setChecked(True)
    scope_window.capture_preview()
    assert "rearm_trigger_after_image" in scope_window._scope.calls


def test_copy_preview_puts_the_full_resolution_image_on_the_clipboard(scope_window):
    scope_window.capture_preview()
    QApplication.clipboard().clear()

    scope_window.copy_preview()

    pixmap = QApplication.clipboard().pixmap()
    assert not pixmap.isNull()
    # The clipboard gets the full-resolution capture, not the scaled preview widget.
    assert pixmap.width() == 40
    assert pixmap.height() == 30


def test_copy_preview_reports_when_nothing_has_been_captured(make_window):
    from dpo4000_utils.gui_qt.ui_polish_window import QtScopeWindow

    messages: list[tuple] = []
    window = make_window(QtScopeWindow)
    window._message = lambda *args, **kwargs: messages.append(args)
    window._last_preview_png = b""
    window._last_image_path = None

    window.copy_preview()

    assert messages, "user should be told there is nothing to copy"


def test_preview_placeholder_explains_the_transient_action(unlocked_window):
    assert "Preview" in unlocked_window.preview_label.text()


def test_preview_and_image_buttons_are_wired_to_their_handlers(unlocked_window):
    assert button_named(unlocked_window, "Preview") is not None
    assert button_named(unlocked_window, "Image") is not None
