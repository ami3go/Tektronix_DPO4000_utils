"""Final DPO4000 Desk file/workflow presentation polish.

This thin final layer keeps the retained-session behavior from
``preview_actions_window`` while simplifying user-facing labels, separating scope
setup JSON controls from output naming, and making full-record CSV export explicit.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractButton,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..gui.config import resolve_output_folder
from .api_window import DEFAULT_RESTORE_TIMEOUT_MS
from .display_window import FILE_PAGE_INDEX
from .preview_actions_window import QtScopeWindow as PreviewQtScopeWindow


class QtScopeWindow(PreviewQtScopeWindow):
    """Final launched window with concise controls and deterministic full-record CSV."""

    @staticmethod
    def _rename_buttons(container: QWidget, replacements: dict[str, str]) -> None:
        for button in container.findChildren(QAbstractButton):
            replacement = replacements.get(button.text())
            if replacement is not None:
                button.setText(replacement)

    # ------------------------------------------------------------------
    # Concise card button labels
    # ------------------------------------------------------------------
    def _build_acquisition_setup_card(self):
        card = super()._build_acquisition_setup_card()
        self._rename_buttons(
            card,
            {
                "Read acquisition setup": "Read",
                "Apply acquisition setup": "Apply",
            },
        )
        return card

    def _build_channel_labels_card(self):
        card = super()._build_channel_labels_card()
        self._rename_buttons(
            card,
            {
                "Read labels": "Read",
                "Apply labels": "Apply",
            },
        )
        return card

    def _build_display_settings_card(self):
        card = super()._build_display_settings_card()
        self._rename_buttons(
            card,
            {
                "Read display": "Read",
                "Apply display": "Apply",
                "Clear text": "Clear",
            },
        )
        return card

    # ------------------------------------------------------------------
    # File page
    # ------------------------------------------------------------------
    def _build_file_tab(self) -> QWidget:
        """Build output-file controls and scope settings as separate cards."""
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)

        output_card = self._card("File output")
        output_layout = QVBoxLayout(output_card)
        output_layout.setSpacing(12)

        folder_row = QWidget()
        folder_row.setObjectName("SettingsFolderRow")
        folder_layout = QHBoxLayout(folder_row)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(8)
        folder_label = QLabel("Destination folder")
        folder_label.setMinimumWidth(132)
        self.output_folder = QLineEdit(str(resolve_output_folder("scope_gui_output")))
        self.output_folder.setMinimumWidth(240)
        self.output_folder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.output_folder, 1)
        folder_layout.addWidget(self._button("Folder", self.pick_output_folder))
        folder_layout.addWidget(self._button("Open", self.open_output_folder))
        output_layout.addWidget(folder_row)

        hint = QLabel("Filename format: <prefix><base><_timestamp optional>.<extension>")
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        output_layout.addWidget(hint)

        png_block, self.png_prefix, self.png_base, self.png_timestamp = self._settings_naming_block(
            "PNG images",
            "scope_",
            "screen",
            True,
        )
        csv_block, self.csv_prefix, self.csv_base, self.csv_timestamp = self._settings_naming_block(
            "CSV waveforms",
            "scope_",
            "waveform",
            True,
        )
        output_layout.addWidget(png_block)
        output_layout.addWidget(csv_block)
        layout.addWidget(self._prepare_drawer_card(output_card))

        scope_settings_card = self._card("Scope settings")
        scope_settings_layout = QVBoxLayout(scope_settings_card)
        scope_settings_layout.setSpacing(12)

        settings_block, self.settings_prefix, self.settings_base, self.settings_timestamp = self._settings_naming_block(
            "Settings JSON",
            "dpo4054_",
            "setup",
            True,
        )
        scope_settings_layout.addWidget(settings_block)

        self.restore_wait_opc = QCheckBox("Wait for *OPC? after restore (can timeout on DPO4000)")
        scope_settings_layout.addWidget(self.restore_wait_opc)

        actions = QWidget()
        actions.setObjectName("ScopeSettingsActionRow")
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)
        save_button = self._button("Save", self.save_settings)
        restore_button = self._accent_button("Restore", self.restore_settings)
        default_button = self._button("Default", self.restore_default_scope_setup)
        for button in (save_button, restore_button, default_button):
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            action_layout.addWidget(button, 1)
        scope_settings_layout.addWidget(actions)
        layout.addWidget(self._prepare_drawer_card(scope_settings_card))

        layout.addStretch(1)
        return self._wrap_scrollable_drawer_page(
            body,
            scroll_name="FileScrollArea",
            body_name="FileScrollBody",
        )

    def open_output_folder(self) -> None:
        """Open the configured output directory in the platform file manager."""
        folder = self._configured_output_folder(create=True).resolve()
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        if opened:
            self.statusBar().showMessage(f"Opened folder: {folder}")
        else:
            self.statusBar().showMessage(f"Could not open folder: {folder}")

    # ------------------------------------------------------------------
    # Full-record CSV and non-modal file workflow feedback
    # ------------------------------------------------------------------
    def save_csv(self) -> None:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        path = self._build_output_path("csv")
        if not self._confirm_or_cancel_overwrite(path):
            return
        path.parent.mkdir(parents=True, exist_ok=True)

        def action(scope) -> tuple[str, int]:
            record_length = int(scope.get_record_length())
            saved_path = scope.save_all_channels_to_single_csv(
                path,
                point_count=record_length,
            )
            return str(saved_path), record_length

        result = self._run_action("Saving enabled channel waveforms to CSV", action)
        if isinstance(result, tuple) and len(result) == 2:
            saved_path = Path(str(result[0]))
            point_count = int(result[1])
            self._last_action = f"CSV saved: {saved_path.name} ({point_count} points)"
            self._update_status_strip()
            self.statusBar().showMessage(self._last_action)

    def save_settings(self) -> None:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        path = self._build_output_path("settings")
        if not self._confirm_or_cancel_overwrite(path):
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        result = self._run_action(
            "Saving scope settings",
            lambda scope: str(scope.save_scope_settings(path, ask_before_overwrite=False)),
        )
        if isinstance(result, str):
            saved_path = Path(result)
            self._last_action = f"Settings saved: {saved_path.name}"
            self._update_status_strip()
            self.statusBar().showMessage(self._last_action)

    def restore_settings(self) -> None:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Restore scope settings JSON",
            str(self._configured_output_folder(create=True)),
            "JSON files (*.json);;All files (*.*)",
        )
        if not selected:
            return

        path = Path(selected)
        wait_opc = self.restore_wait_opc.isChecked()
        result = self._run_action(
            "Restoring scope settings",
            lambda scope: scope.apply_scope_settings(
                path,
                wait_complete=wait_opc,
                check_error=True,
                opc_timeout_ms=DEFAULT_RESTORE_TIMEOUT_MS,
            ),
        )
        if isinstance(result, dict):
            self._last_action = f"Settings restored: {path.name}"
            self._update_status_strip()
            self.statusBar().showMessage(self._last_action)

    def restore_default_scope_setup(self) -> None:
        """Apply the scope factory/default setup through the public driver API."""
        result = self._run_action(
            "Restoring scope default setup",
            lambda scope: scope.restore_default_setup(),
        )
        if result is None:
            return
        self.refresh_scope_parameters()
        self._last_action = "Scope default setup restored"
        self._update_status_strip()
        self.statusBar().showMessage(self._last_action)


__all__ = ["QtScopeWindow"]
