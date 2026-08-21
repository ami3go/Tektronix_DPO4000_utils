"""Launched PySide6 window with clickable collapsible card headers."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QSizePolicy, QVBoxLayout, QWidget

from .acquisition_window import QtScopeWindow as AcquisitionQtScopeWindow


class CollapsibleCard(QGroupBox):
    """A compact collapsible card where the card title/header toggles the body."""

    _HEADER_HEIGHT = 34

    def __init__(self, title: str, content: QWidget, *, expanded: bool = True) -> None:
        super().__init__()
        self._base_title = title
        self._content = content
        self._expanded = False
        self.setObjectName("InlineCollapsibleCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(f"Click the {title} card header to collapse or expand.")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(content)

        self.set_expanded(expanded)

    def set_expanded(self, expanded: bool) -> None:
        """Show or hide the body while keeping the card header visible."""
        self._expanded = expanded
        self._content.setVisible(expanded)
        self.setTitle(("▾ " if expanded else "▸ ") + self._base_title)

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
