"""Stable PySide6 window with a compact titleless preview panel.

The launched left preview panel no longer uses a visible QGroupBox title or the
empty QGroupBox title band.  This keeps the status strip and quick controls tight
under the top navigation.
"""

from __future__ import annotations

from PySide6.QtWidgets import QGroupBox

from .measurement_window import QtScopeWindow as MeasurementQtScopeWindow

UNTITLED_PREVIEW_CARD_QSS = """
QGroupBox#UntitledPreviewCard {
    margin-top: 0px;
    padding-top: 0px;
}
QGroupBox#UntitledPreviewCard::title {
    height: 0px;
    margin: 0px;
    padding: 0px;
    color: transparent;
}
"""


class QtScopeWindow(MeasurementQtScopeWindow):
    """Stable launched Qt window with no reserved preview-title gap."""

    def _build_preview_card(self) -> QGroupBox:
        """Remove the unused preview title band, not only the title text."""
        card = super()._build_preview_card()
        card.setTitle("")
        card.setObjectName("UntitledPreviewCard")
        card.setContentsMargins(0, 0, 0, 0)
        card.setStyleSheet(UNTITLED_PREVIEW_CARD_QSS)
        layout = card.layout()
        if layout is not None:
            layout.setContentsMargins(10, 8, 10, 10)
            layout.setSpacing(8)
        return card


__all__ = ["QtScopeWindow", "UNTITLED_PREVIEW_CARD_QSS"]
