"""Final DPO4000 Desk Preview/Image and optional retained-session semantics.

The user-facing quick actions distinguish transient screen preview from persistent
image save. Connection options can additionally retain one VISA session between
operations; when disabled the established open/operate/close lifecycle is used.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from ..errors import is_transport_error
from .bus_window import QtScopeWindow as BusQtScopeWindow
from .scope_worker import PersistentScopeSession

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
    """Final launched window with Preview/Image and optional persistent VISA session."""

    def __init__(self, *args, **kwargs) -> None:
        self._persistent_scope_session: PersistentScopeSession | None = None
        self._persistent_session_dirty = False
        super().__init__(*args, **kwargs)
        self.keep_session.toggled.connect(self._on_keep_session_toggled)
        self._connect_persistent_session_invalidation_signals()

    # ------------------------------------------------------------------
    # Connection-session policy
    # ------------------------------------------------------------------
    def _build_connection_tab(self):
        page = super()._build_connection_tab()
        body = page.widget() if hasattr(page, "widget") else page
        options_card = None
        if body is not None:
            for card in body.findChildren(QGroupBox):
                if card.title() == "Connection options":
                    options_card = card
                    break

        if options_card is None:
            options_card = self._card("Connection options")
            form = QFormLayout(options_card)
            self._prepare_form(form)
            layout = body.layout() if body is not None else None
            if layout is not None:
                insert_index = max(0, layout.count() - 1)
                layout.insertWidget(insert_index, options_card)
        else:
            form = options_card.layout()

        self.keep_session = QCheckBox("Keep session")
        self.keep_session.setChecked(False)
        self.keep_session.setToolTip(
            "Keep one VISA connection open and reuse it across scope operations. "
            "Disable to open and close a new session for every operation."
        )
        if isinstance(form, QFormLayout):
            form.addRow(self.keep_session)
            hint = QLabel(
                "Enabled: reuse one worker-owned VISA session for faster repeated operations "
                "such as Preview. Disabled: open and close the scope for every operation."
            )
            hint.setObjectName("MutedLabel")
            hint.setWordWrap(True)
            form.addRow(hint)
        return page

    def _apply_preferences(self, preferences) -> None:
        super()._apply_preferences(preferences)
        if hasattr(self, "keep_session"):
            self.keep_session.setChecked(bool(getattr(preferences, "keep_session", False)))

    def _collect_preferences(self):
        preferences = super()._collect_preferences()
        if hasattr(self, "keep_session"):
            preferences.keep_session = self.keep_session.isChecked()
        return preferences

    def _connect_persistent_session_invalidation_signals(self) -> None:
        """Close a retained session when its selected connection definition changes."""
        self.resource.currentTextChanged.connect(self._on_connection_definition_changed)
        self.eth_host.textChanged.connect(self._on_connection_definition_changed)
        self.eth_port.textChanged.connect(self._on_connection_definition_changed)
        self.eth_protocol.currentTextChanged.connect(self._on_connection_definition_changed)
        self.usb_mode.toggled.connect(self._on_connection_definition_changed)
        self.eth_mode.toggled.connect(self._on_connection_definition_changed)

    def _on_keep_session_toggled(self, checked: bool) -> None:
        if checked:
            self.statusBar().showMessage(
                "Keep session enabled; the next scope operation will open and retain VISA"
            )
            return
        self._release_persistent_scope_session()
        self.statusBar().showMessage("Keep session disabled; using one VISA session per operation")

    def _on_connection_definition_changed(self, *_args) -> None:
        manager = self._persistent_scope_session
        if manager is None or not self.keep_session.isChecked():
            return
        if getattr(self, "_operation_active", False):
            self._persistent_session_dirty = True
            return
        self._release_persistent_scope_session()
        self.statusBar().showMessage(
            "Connection changed; retained session will reopen on the next operation"
        )

    def _persistent_session_manager(self) -> PersistentScopeSession:
        manager = self._persistent_scope_session
        if manager is None:
            manager = PersistentScopeSession(parent=self)
            self._persistent_scope_session = manager
        return manager

    def _release_persistent_scope_session(self, *, log: bool = True) -> None:
        manager = self._persistent_scope_session
        self._persistent_scope_session = None
        self._persistent_session_dirty = False
        if manager is None:
            return
        result = manager.shutdown()
        manager.deleteLater()
        if result.error is not None:
            if log:
                self._append_log(f"Could not close retained scope session: {result.error}")
            return
        if log:
            self._append_log("Retained scope session closed")

    def _finish_non_transport_action_error(self, description: str, exc: BaseException) -> None:
        """Report validation/protocol errors without visually dropping a kept connection."""
        error_text = str(exc).strip() or exc.__class__.__name__
        self._operation_active = False
        self._last_action = f"Failed: {description}"
        self.statusBar().showMessage(f"Failed: {description}")
        self._append_log(f"ERROR: {error_text}")
        self._update_scope_control_enabled()
        self._update_status_strip()
        self._message(description, error_text, error=True)
        return

    def _run_action(self, description: str, callback: Callable[[Any], object]) -> object | None:
        keep_session = getattr(self, "keep_session", None)
        if keep_session is None or not keep_session.isChecked():
            return super()._run_action(description, callback)

        # The retained-session path does not delegate to super(), so it needs the
        # same re-entry guard; here re-entry would also queue a second request
        # behind the one the nested event loop is still waiting on.
        if self._reject_reentrant_scope_action(description):
            return None

        self._operation_active = True
        self._last_action = description
        self.statusBar().showMessage(description)
        self._append_log(description)
        self._update_scope_control_enabled()
        self._update_status_strip()
        self.keep_session.setEnabled(False)

        try:
            resource = self._selected_resource()
            timeout_ms = self._timeout()
        except Exception as exc:  # noqa: BLE001 - exact GUI validation diagnostic.
            self.keep_session.setEnabled(True)
            return self._finish_non_transport_action_error(description, exc)

        manager = self._persistent_session_manager()
        try:
            result = manager.execute(resource, timeout_ms, callback)
        finally:
            self.keep_session.setEnabled(True)

        if self._persistent_session_dirty:
            self._release_persistent_scope_session()

        if result.error is not None:
            if is_transport_error(result.error):
                return self._finish_scope_action_error(description, result.error)
            return self._finish_non_transport_action_error(description, result.error)
        return self._finish_scope_action_success(description, result.value)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API name.
        if getattr(self, "_operation_active", False) and self._persistent_scope_session is not None:
            self.statusBar().showMessage("A scope operation is still active; close after it finishes")
            event.ignore()
            return
        self._release_persistent_scope_session(log=False)
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Preview / image actions
    # ------------------------------------------------------------------
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
        rearm = self._rearm_after_image_enabled()
        trigger_channel = self._trigger_channel_or_none()

        def action(scope) -> bytes:
            png_data = bytes(scope.read_screen_png())
            if rearm:
                scope.rearm_trigger_after_image(trigger_channel=trigger_channel)
            return png_data

        result = self._run_action("Refreshing scope preview", action)
        if isinstance(result, (bytes, bytearray, memoryview)):
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
        rearm = self._rearm_after_image_enabled()
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
