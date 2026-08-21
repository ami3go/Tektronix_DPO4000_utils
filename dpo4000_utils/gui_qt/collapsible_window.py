"""Launched PySide6 window with compact clickable collapsible cards."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from .acquisition_window import QtScopeWindow as AcquisitionQtScopeWindow

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
"""


class CollapsibleCard(QGroupBox):
    """A compact collapsible card where the card header itself toggles the body."""

    _HEADER_HEIGHT = 34
    _EXPANDED_OBJECT_NAME = "InlineCollapsibleCard"
    _COLLAPSED_OBJECT_NAME = "InlineCollapsibleCardCollapsed"

    def __init__(self, title: str, content: QWidget, *, expanded: bool = True) -> None:
        super().__init__()
        self._base_title = title
        self._content = content
        self._expanded = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(f"Click the {title} card header to collapse or expand.")

        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(0)
        self._layout.addWidget(content)

        self.set_expanded(expanded)

    def _refresh_style(self) -> None:
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()

    def set_expanded(self, expanded: bool) -> None:
        """Show or hide the body; collapsed cards keep only the clickable title strip."""
        self._expanded = expanded
        self._content.setVisible(expanded)
        self.setTitle(("▾ " if expanded else "▸ ") + self._base_title)
        self.setObjectName(self._EXPANDED_OBJECT_NAME if expanded else self._COLLAPSED_OBJECT_NAME)

        if expanded:
            self._layout.setContentsMargins(12, 10, 12, 12)
            self.setMinimumHeight(0)
            self.setMaximumHeight(16_777_215)
        else:
            self._layout.setContentsMargins(0, 0, 0, 0)
            self.setMinimumHeight(self._HEADER_HEIGHT)
            self.setMaximumHeight(self._HEADER_HEIGHT)

        self._refresh_style()
        self.updateGeometry()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override name.
        """Toggle only when the compact card header area is clicked."""
        if event.button() == Qt.MouseButton.LeftButton and event.pos().y() <= self._HEADER_HEIGHT:
            self.set_expanded(not self._expanded)
            event.accept()
            return
        super().mousePressEvent(event)


class QtScopeWindow(AcquisitionQtScopeWindow):
    """Launched Qt window using card-header collapse instead of extra header buttons."""

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
        """Convert direct plain QGroupBox cards in a page into clickable cards."""
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
        """Wrap a normal card so all cards share the same collapsible behavior."""
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


__all__ = [
    "CollapsibleCard",
    "PREVIEW_CONTROL_GUTTER_QSS",
    "PREVIEW_CONTROL_GUTTER_WIDTH",
    "QtScopeWindow",
]
