"""Launched PySide6 window with compact clickable collapsible cards."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QSizePolicy, QVBoxLayout, QWidget

from .acquisition_window import QtScopeWindow as AcquisitionQtScopeWindow


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

    def _collapsible_section(self, title: str, content: QWidget, *, expanded: bool = True) -> QWidget:
        """Use the card title/header as the collapse control to save vertical space."""
        if isinstance(content, QGroupBox):
            content.setTitle("")
            content.setObjectName("InlineCollapsibleContent")
            content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._prepare_drawer_card(content)
        else:
            content.setObjectName("InlineCollapsibleContent")

        card = CollapsibleCard(title, content, expanded=expanded)
        return self._register_advanced_widget(card)


__all__ = ["CollapsibleCard", "QtScopeWindow"]
