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
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..gui.config import resolve_output_folder
from .acquisition_window import QtScopeWindow as AcquisitionQtScopeWindow

WINDOW_TITLE = "Tektronix dpo4000"
PREVIEW_CONTROL_GUTTER_WIDTH = 12
CONTROL_PAGE_BUILDERS = (
    "_build_connection_tab",
    "_build_channels_tab",
    "_build_measurement_tab",
    "_build_trigger_tab",
    "_build_acquisition_tab",
    "_build_settings_tab",
    "_build_log_tab",
)
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

    def __init__(
        self,
        title: str,
        content: QWidget,
        *,
        expanded: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._base_title = title
        self._content = content
        self._expanded = False
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setObjectName(self._EXPANDED_OBJECT_NAME)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(f"Click the {title} card header to collapse or expand.")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._header = QLabel(self)
        self._header.setObjectName("InlineCollapsibleHeader")
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setMinimumHeight(34)
        self._header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._layout.addWidget(self._header)

        self._content_shell = QWidget(self)
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
        self._pending_preferences = None
        self._lazy_control_pages_built: list[bool] = []
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
            layout = bar.layout()
            title.hide()
            if layout is not None:
                layout.removeWidget(title)
            title.deleteLater()
        return bar

    def _build_control_stack(self) -> QStackedWidget:
        """Create placeholder pages and build real control pages only when opened.

        Qt creates hidden top-level popup widgets for every QComboBox. Building all
        pages at startup therefore creates many popup windows before the main
        window is visible. Lazy pages keep startup to the preview plus the first
        selected control page.
        """
        stack = QStackedWidget()
        stack.setObjectName("RightControlStack")
        self._lazy_control_pages_built = [False for _ in CONTROL_PAGE_BUILDERS]
        for index, _builder_name in enumerate(CONTROL_PAGE_BUILDERS):
            placeholder = QWidget()
            placeholder.setObjectName(f"LazyControlPagePlaceholder{index}")
            stack.addWidget(placeholder)
        return stack

    def _select_drawer_page(self, index: int) -> None:
        """Build the selected page on demand, then show it in the right panel."""
        self._ensure_control_page_built(index)
        super()._select_drawer_page(index)

    def _ensure_control_page_built(self, index: int) -> None:
        """Build a right-side control page only once, just before it is shown."""
        stack = getattr(self, "control_stack", None)
        if stack is None or index < 0 or index >= len(CONTROL_PAGE_BUILDERS):
            return
        if index < len(self._lazy_control_pages_built) and self._lazy_control_pages_built[index]:
            return

        builder = getattr(self, CONTROL_PAGE_BUILDERS[index])
        page = builder()
        page = self._make_page_cards_collapsible(page)

        placeholder = stack.widget(index)
        stack.removeWidget(placeholder)
        placeholder.deleteLater()
        stack.insertWidget(index, page)
        self._lazy_control_pages_built[index] = True

        self._apply_preferences_to_built_widgets()
        update_controls = getattr(self, "_update_scope_control_enabled", None)
        if callable(update_controls):
            update_controls()

    def _make_page_cards_collapsible(self, page: QWidget) -> QWidget:
        """Convert direct plain QGroupBox cards without creating parentless windows."""
        body = page.widget() if isinstance(page, QScrollArea) else page
        layout = body.layout() if body is not None else None
        if layout is None:
            return page

        plain_card_index = 0
        index = 0
        while index < layout.count():
            item = layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if not isinstance(widget, QGroupBox) or isinstance(widget, CollapsibleCard):
                index += 1
                continue

            widget.hide()
            layout.removeWidget(widget)
            replacement = self._wrap_plain_card(
                widget,
                expanded=plain_card_index == 0,
                parent=body,
            )
            layout.insertWidget(index, replacement)
            replacement.show()
            plain_card_index += 1
            index += 1
        return page

    def _wrap_plain_card(self, card: QGroupBox, *, expanded: bool, parent: QWidget) -> CollapsibleCard:
        """Wrap a normal card so all cards share the same lightweight behavior."""
        title = card.title().strip() or "Section"
        card.setWindowFlags(Qt.WindowType.Widget)
        card.setTitle("")
        card.setObjectName("InlineCollapsibleContent")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        AcquisitionQtScopeWindow._prepare_drawer_card(card)
        card.show()
        return CollapsibleCard(title, card, expanded=expanded, parent=parent)

    def _collapsible_section(self, title: str, content: QWidget, *, expanded: bool = False) -> QWidget:
        """Use the card title/header as the collapse control to save vertical space."""
        if isinstance(content, QGroupBox):
            content.setWindowFlags(Qt.WindowType.Widget)
            content.setTitle("")
            content.setObjectName("InlineCollapsibleContent")
            content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            AcquisitionQtScopeWindow._prepare_drawer_card(content)
        else:
            content.setObjectName("InlineCollapsibleContent")

        card = CollapsibleCard(title, content, expanded=expanded)
        return self._register_advanced_widget(card)

    # ------------------------------------------------------------------
    # Preferences and lazy pages
    # ------------------------------------------------------------------
    def _apply_preferences(self, preferences) -> None:
        """Apply preferences only to pages that have already been built."""
        self._pending_preferences = preferences
        self._apply_preferences_to_built_widgets()

    def _apply_preferences_to_built_widgets(self) -> None:
        preferences = getattr(self, "_pending_preferences", None)
        if preferences is None:
            return

        if hasattr(self, "eth_host"):
            self.eth_host.setText(preferences.ethernet_host)
            self.eth_port.setText(preferences.ethernet_port)
            self._set_combo_text(self.eth_protocol, preferences.ethernet_protocol)
            self.timeout_ms.setText(preferences.timeout_ms)
            self._update_visa_resource_list((preferences.visa_resource,))
            self._set_combo_text(self.resource, preferences.visa_resource)
            if preferences.connection_mode == "ethernet":
                self.eth_mode.setChecked(True)
            else:
                self.usb_mode.setChecked(True)
            self._refresh_generated_ethernet_resource()

        if hasattr(self, "output_folder"):
            self.output_folder.setText(preferences.output_folder)
            self.png_prefix.setText(preferences.png_prefix)
            self.png_base.setText(preferences.png_base)
            self.png_timestamp.setChecked(preferences.png_add_timestamp)
            self.csv_prefix.setText(preferences.csv_prefix)
            self.csv_base.setText(preferences.csv_base)
            self.csv_timestamp.setChecked(preferences.csv_add_timestamp)
            self.settings_prefix.setText(preferences.settings_prefix)
            self.settings_base.setText(preferences.settings_base)
            self.settings_timestamp.setChecked(preferences.settings_add_timestamp)
            self.restore_wait_opc.setChecked(preferences.restore_wait_opc)

        if hasattr(self, "rearm_after_image"):
            self.rearm_after_image.setChecked(preferences.rearm_after_image)
            self._set_combo_text(self.trigger_channel_after_image, preferences.trigger_channel_after_image)

        if hasattr(self, "trigger_channel"):
            self._set_combo_text(self.trigger_channel, preferences.trigger_setup_channel)
            self.trigger_level.setText(preferences.trigger_level)
            self.trigger_set_source.setChecked(preferences.trigger_set_source)

    def _collect_preferences(self):
        """Build preference-bearing pages before saving preferences on close."""
        for index in (0, 3, 5):
            self._ensure_control_page_built(index)
        return super()._collect_preferences()

    def capture_preview(self) -> None:
        self._ensure_control_page_built(3)
        return super().capture_preview()

    def save_png_image(self) -> None:
        self._ensure_control_page_built(5)
        return super().save_png_image()

    def save_csv(self) -> None:
        self._ensure_control_page_built(5)
        return super().save_csv()

    def save_settings(self) -> None:
        self._ensure_control_page_built(5)
        return super().save_settings()

    def restore_settings(self) -> None:
        self._ensure_control_page_built(5)
        return super().restore_settings()

    # ------------------------------------------------------------------
    # Settings page layout
    # ------------------------------------------------------------------
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
    "CONTROL_PAGE_BUILDERS",
    "PREVIEW_CONTROL_GUTTER_QSS",
    "PREVIEW_CONTROL_GUTTER_WIDTH",
    "WINDOW_TITLE",
    "QtScopeWindow",
]
