"""Final DPO4000 Desk Preview/Image action semantics.

The user-facing quick actions intentionally distinguish a transient in-memory
screen preview from a persistent PNG image save.  Instrument access remains
through the public driver API inherited from the existing desktop stack.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget

from .bus_window import QtScopeWindow as BusQtScopeWindow


QUICK_ACTION_TOOLTIPS = {
    "IDN": "Test connection and unlock scope controls",
    "Preview": "F5 · Refresh the scope screen preview without saving a file",
    "Copy": "Copy the current full-resolution preview image to the clipboard",
    "Image": "Ctrl+S · Save the scope screen as a PNG image and refresh the preview",
    "CSV": "Ctrl+Shift+S · Save enabled channels to CSV",
    "Run": "F6 · Start acquisition",
    "Stop": "F7 · Stop acquisition",
    "Single": "F8 · Start single acquisition",
    "Force": "Force one trigger event",
}


class QtScopeWindow(BusQtScopeWindow):
    """Final launched window with distinct transient Preview and saved Image actions."""

    def _build_preview_card(self):
        card = super()._build_preview_card()
        self.preview_label.setText("Select Preview to refresh the scope screen here.")
        return card

    def _build_quick_control_bar(self) -> QWidget:
        """Build the quick actions using unambiguous Preview and Image labels."""
        toolbar = QWidget()
        toolbar.setObjectName("QuickControlBar")
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        quick_actions = (
            ("IDN", self.test_connection, False),
            ("Preview", self.capture_preview, False),
            ("Copy", self.copy_preview, False),
            ("Image", self.save_png_image, False),
            ("CSV", self.save_csv, False),
            ("Run", self.run_acquisition, False),
            ("Stop", self.stop_acquisition, False),
            ("Single", self.single_acquisition, False),
            ("Force", self.force_trigger, True),
        )
        for text, callback, accent in quick_actions:
            button = self._quick_button(text, callback, accent=accent)
            tooltip = QUICK_ACTION_TOOLTIPS.get(text)
            if tooltip:
                button.setToolTip(tooltip)
            layout.addWidget(button)
        layout.addStretch(1)
        return toolbar

    def _show_preview_png(self, png_data: bytes) -> bool:
        """Decode full-resolution PNG bytes and update the scaled preview widget."""
        data = bytes(png_data)
        pixmap = QPixmap()
        if not data or not pixmap.loadFromData(data):
            self._message("Preview", "Scope image could not be decoded as PNG data.")
            return False

        self._last_preview_png = data
        self.preview_label.setPixmap(
            pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        return True

    def capture_preview(self) -> None:
        """Refresh the screen preview entirely in memory; do not create a user file."""
        rearm = self.rearm_after_image.isChecked()
        trigger_channel = self._trigger_channel_or_none()

        def action(scope) -> bytes:
            png_data = bytes(scope.read_screen_png())
            if rearm:
                scope.rearm_trigger_after_image(trigger_channel=trigger_channel)
            return png_data

        result = self._run_action("Refreshing scope preview", action)
        if isinstance(result, (bytes, bytearray, memoryview)):
            # Preview is intentionally transient.  Clear the saved-image marker so
            # callers cannot mistake the current preview for a persisted file.
            self._last_image_path = None
            if self._show_preview_png(bytes(result)):
                self.statusBar().showMessage("Scope preview refreshed (not saved)")

    def save_png_image(self) -> None:
        """Save a persistent PNG image using the configured naming/output settings."""
        path = self._build_output_path("png")
        if not self._confirm_or_cancel_overwrite(path):
            return
        self._capture_image_to(path, "Saving scope image")

    def _capture_image_to(self, path: Path, description: str) -> None:
        """Save a PNG image and make the saved full-resolution image the current preview."""
        path.parent.mkdir(parents=True, exist_ok=True)
        rearm = self.rearm_after_image.isChecked()
        trigger_channel = self._trigger_channel_or_none()

        def action(scope) -> str:
            saved_path = scope.save_image_path(path)
            if rearm:
                scope.rearm_trigger_after_image(trigger_channel=trigger_channel)
            return str(saved_path)

        result = self._run_action(description, action)
        if isinstance(result, str):
            saved_path = Path(result)
            self._last_image_path = saved_path
            try:
                png_data = saved_path.read_bytes()
            except OSError:
                # Retain the established file-backed fallback if the image was
                # successfully saved but cannot immediately be re-read.
                self._load_preview(saved_path)
                return
            self._show_preview_png(png_data)

    def copy_preview(self) -> None:
        """Copy the current full-resolution preview, whether transient or file-backed."""
        png_data = bytes(getattr(self, "_last_preview_png", b""))
        source_text = "in-memory preview"

        if not png_data:
            saved_path = getattr(self, "_last_image_path", None)
            if isinstance(saved_path, Path) and saved_path.exists():
                try:
                    png_data = saved_path.read_bytes()
                    source_text = str(saved_path)
                except OSError:
                    png_data = b""

        if not png_data:
            self._message("Copy preview", "No captured preview image is available yet.")
            return

        pixmap = QPixmap()
        if not pixmap.loadFromData(png_data):
            self._message("Copy preview", "Captured preview could not be decoded.")
            return

        QApplication.clipboard().setPixmap(pixmap)
        self._append_log(f"Copied preview to clipboard: {source_text}")
        self.statusBar().showMessage("Preview copied to clipboard")


__all__ = ["QtScopeWindow"]
