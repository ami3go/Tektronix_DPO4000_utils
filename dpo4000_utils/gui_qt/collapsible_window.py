"""Launched PySide6 window with compact clickable collapsible cards."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..gui.config import resolve_output_folder
from .acquisition_window import QtScopeWindow as AcquisitionQtScopeWindow

WINDOW_TITLE = "Tektronix dpo4000"
PREVIEW_CONTROL_GUTTER_WIDTH = 12
PREVIEW_CONTROL_GUTTER_QSS = """
QSplitter#MainSplitter::handle {
    background: #111827;
    border: 0;
    margin: 0;
    width: 12px;
}

QSplitter#MainSplitter::handle:hover {
    background: #1f2937;
    border-left: 1px solid #253142;
    border-right: 1px solid #253142;
}

QWidget#RightControlPanel {
    background: #111827;
    border: 1px solid #2b3544;
    border-radius: 8px;
}

QFrame#InlineCollapsibleCard,
QFrame#InlineCollapsibleCardCollapsed {
    background: #1f2937;
    border: 1px solid #374151;
    border-radius: 8px;
}

QFrame#InlineCollapsibleCard:hover,
QFrame#InlineCollapsibleCardCollapsed:hover {
    border-color: #4b5563;
}

QLabel#InlineCollapsibleHeader {
    background: #253142;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    color: #ffffff;
    font-weight: 700;
    padding: 8px 12px;
}

QFrame#InlineCollapsibleCard QLabel#InlineCollapsibleHeader {
    border-bottom: 1px solid #374151;
}

QFrame#InlineCollapsibleCardCollapsed QLabel#InlineCollapsibleHeader {
    border-bottom: 0;
    border-bottom-left-radius: 7px;
    border-bottom-right-radius: 7px;
}

QWidget#InlineCollapsibleBody,
QGroupBox#InlineCollapsibleContent {
    background: transparent;
    border: 0;
    margin: 0;
    padding: 0;
    font-weight: 400;
}

QGroupBox#InlineCollapsibleContent::title {
    color: transparent;
    padding: 0;
}
"""


class CollapsibleCard(QFrame):
    """A lightweight collapsible card where the card header itself toggles the body."""

    _EXPANDED_OBJECT_NAME = "InlineCollapsibleCard"
    _COLLAPSED_OBJECT_NAME = "InlineCollapsibleCardCollapsed"

    def __init__(self, title: str, content: QWidget, *, expanded: bool = True) -> None:
        super().__init__()
        self._base_title = title
        self._content = content
        self._expanded = False
        self.setObjectName(self._EXPANDED_OBJECT_NAME)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(f"Click the {title} card header to collapse or expand.")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._header = QLabel()
        self._header.setObjectName("InlineCollapsibleHeader")
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setMinimumHeight(34)
        self._header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._layout.addWidget(self._header)

        self._content_shell = QWidget()
        self._content_shell.setObjectName("InlineCollapsibleBody")
        shell_layout = QVBoxLayout(self._content_shell)
        shell_layout.setContentsMargins(12, 10, 12, 12)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(content)
        self._layout.addWidget(self._content_shell)

        self.set_expanded(expanded)

    def _refresh_style(self) -> None:
        for widget in (self, self._header, self._content_shell):
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)
            widget.update()

    def set_expanded(self, expanded: bool) -> None:
        """Show or hide the body; collapsed cards keep only the clickable title strip."""
        self._expanded = expanded
        self._content_shell.setVisible(expanded)
        self._header.setText(("▾ " if expanded else "▸ ") + self._base_title)
        self.setObjectName(self._EXPANDED_OBJECT_NAME if expanded else self._COLLAPSED_OBJECT_NAME)
        self.setMaximumHeight(16_777_215)
        self.setMinimumHeight(0)
        self._refresh_style()
        self.updateGeometry()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override name.
        """Toggle only when the compact card header area is clicked."""
        if event.button() == Qt.MouseButton.LeftButton and self._header.geometry().contains(event.pos()):
            self.set_expanded(not self._expanded)
            event.accept()
            return
        super().mousePressEvent(event)


class QtScopeWindow(AcquisitionQtScopeWindow):
    """Launched Qt window using lightweight card-header collapse."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setWindowTitle(WINDOW_TITLE)

    def _build_ui(self) -> None:
        """Build the UI, then make the preview/control split read as a clean gutter."""
        super()._build_ui()
        self._apply_preview_control_gutter()

    def _apply_preview_control_gutter(self) -> None:
        """Use a subtle 12 px gutter between device preview and control panel."""
        self.main_splitter.setHandleWidth(PREVIEW_CONTROL_GUTTER_WIDTH)
        self.main_splitter.setStyleSheet(PREVIEW_CONTROL_GUTTER_QSS)
        right_panel = self.findChild(QWidget, "RightControlPanel")
        if right_panel is not None:
            right_panel.setStyleSheet(PREVIEW_CONTROL_GUTTER_QSS)

    def _build_application_menu_bar(self) -> QWidget:
        """Build the top menu row without duplicating the application title."""
        bar = super()._build_application_menu_bar()
        title = bar.findChild(QLabel, "ApplicationMenuTitle")
        if title is not None:
            title.setParent(None)
            title.deleteLater()
        return bar

    def _build_control_stack(self):
        """Build pages, then make every direct card collapsible.

        The first plain card on each page remains expanded by default because it is
        the currently-open/primary card for that page. Secondary cards and explicit
        advanced sections start collapsed and can be opened from their card header.
        """
        stack = super()._build_control_stack()
        for index in range(stack.count()):
            self._make_page_cards_collapsible(stack.widget(index))
        return stack

    def _make_page_cards_collapsible(self, page: QWidget) -> QWidget:
        """Convert direct plain QGroupBox cards in a page into lightweight clickable cards."""
        body = page.widget() if isinstance(page, QScrollArea) else page
        layout = body.layout() if body is not None else None
        if layout is None:
            return page

        plain_card_index = 0
        for index in range(layout.count()):
            item = layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if not isinstance(widget, QGroupBox) or isinstance(widget, CollapsibleCard):
                continue

            replacement = self._wrap_plain_card(
                widget,
                expanded=plain_card_index == 0,
            )
            layout.removeWidget(widget)
            layout.insertWidget(index, replacement)
            plain_card_index += 1
        return page

    def _wrap_plain_card(self, card: QGroupBox, *, expanded: bool) -> CollapsibleCard:
        """Wrap a normal card so all cards share the same lightweight behavior."""
        title = card.title().strip() or "Section"
        card.setTitle("")
        card.setObjectName("InlineCollapsibleContent")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        AcquisitionQtScopeWindow._prepare_drawer_card(card)
        return CollapsibleCard(title, card, expanded=expanded)

    def _collapsible_section(self, title: str, content: QWidget, *, expanded: bool = False) -> QWidget:
        """Use the card title/header as the collapse control to save vertical space."""
        if isinstance(content, QGroupBox):
            content.setTitle("")
            content.setObjectName("InlineCollapsibleContent")
            content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            AcquisitionQtScopeWindow._prepare_drawer_card(content)
        else:
            content.setObjectName("InlineCollapsibleContent")

        card = CollapsibleCard(title, content, expanded=expanded)
        return self._register_advanced_widget(card)

    def _build_settings_tab(self) -> QWidget:
        """Build settings with readable full-width naming fields."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)

        card = self._card("Output and scope settings")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(12)

        folder_row = QWidget()
        folder_row.setObjectName("SettingsFolderRow")
        folder_layout = QHBoxLayout(folder_row)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(8)
        folder_label = QLabel("Destination folder")
        folder_label.setMinimumWidth(132)
        self.output_folder = QLineEdit(str(resolve_output_folder("scope_gui_output")))
        self.output_folder.setMinimumWidth(260)
        self.output_folder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.output_folder, 1)
        folder_layout.addWidget(self._button("Pick folder", self.pick_output_folder))
        card_layout.addWidget(folder_row)

        hint = QLabel("Filename format: <prefix><base><_timestamp optional>.<extension>")
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        card_layout.addWidget(hint)

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
        settings_block, self.settings_prefix, self.settings_base, self.settings_timestamp = self._settings_naming_block(
            "Settings JSON",
            "dpo4054_",
            "setup",
            True,
        )
        card_layout.addWidget(png_block)
        card_layout.addWidget(csv_block)
        card_layout.addWidget(settings_block)

        self.restore_wait_opc = QCheckBox("Wait for *OPC? after restore (can timeout on DPO4000)")
        card_layout.addWidget(self.restore_wait_opc)

        actions = QWidget()
        actions.setObjectName("SettingsActionRow")
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)
        save_button = self._button("Save settings JSON", self.save_settings)
        restore_button = self._accent_button("Restore settings JSON...", self.restore_settings)
        save_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        restore_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        action_layout.addWidget(save_button, 1)
        action_layout.addWidget(restore_button, 1)
        card_layout.addWidget(actions)

        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _settings_naming_block(
        self,
        title: str,
        default_prefix: str,
        default_base: str,
        timestamp: bool,
    ) -> tuple[QWidget, QLineEdit, QLineEdit, QCheckBox]:
        """Build a readable filename naming block with full-width text fields."""
        block = QWidget()
        block.setObjectName("SettingsNamingBlock")
        layout = QVBoxLayout(block)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(7)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title_label = QLabel(title)
        title_label.setObjectName("SettingsNamingTitle")
        timestamp_check = QCheckBox("Timestamp")
        timestamp_check.setChecked(timestamp)
        header.addWidget(title_label, 1)
        header.addWidget(timestamp_check)
        layout.addLayout(header)

        prefix = QLineEdit(default_prefix)
        prefix.setMinimumWidth(180)
        prefix.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        base = QLineEdit(default_base)
        base.setMinimumWidth(220)
        base.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout.addWidget(self._settings_text_field_row("Prefix", prefix))
        layout.addWidget(self._settings_text_field_row("Base", base))
        return block, prefix, base, timestamp_check

    @staticmethod
    def _settings_text_field_row(label_text: str, editor: QLineEdit) -> QWidget:
        row = QWidget()
        row.setObjectName("SettingsTextFieldRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        label = QLabel(label_text)
        label.setMinimumWidth(52)
        layout.addWidget(label)
        layout.addWidget(editor, 1)
        return row


__all__ = [
    "CollapsibleCard",
    "PREVIEW_CONTROL_GUTTER_QSS",
    "PREVIEW_CONTROL_GUTTER_WIDTH",
    "WINDOW_TITLE",
    "QtScopeWindow",
]
