"""Experimental PySide6 window with page buttons in a custom title bar.

This branch intentionally uses a frameless Qt window so the application page
buttons can live in the same top row as the window title.  It keeps native OS
window decoration out of the way, but provides basic drag, double-click maximize,
minimize, maximize/restore, close, and status-bar size-grip behavior.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .acquisition_window import (
    PREVIEW_MIN_WIDTH,
    RIGHT_PANEL_DEFAULT_WIDTH,
    RIGHT_PANEL_MAX_WIDTH,
    RIGHT_PANEL_MIN_WIDTH,
)
from .display_window import CONTROL_TAB_TITLES
from .preview_window import QtScopeWindow as PreviewQtScopeWindow

TITLEBAR_WINDOW_TITLE = "Tektronix dpo4000"
TITLEBAR_TABS_QSS = """
QWidget#TitlebarTabsBar {
    background: #111827;
    border-bottom: 1px solid #2b3544;
}

QLabel#TitlebarWindowTitle {
    color: #ffffff;
    font-weight: 700;
    padding: 0 12px 0 4px;
}

QToolButton#TitlebarTabButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: #e5e7eb;
    font-weight: 600;
    padding: 7px 12px;
}

QToolButton#TitlebarTabButton:hover {
    background: #1f2937;
    border-color: #374151;
}

QToolButton#TitlebarTabButton:checked {
    background: #2563eb;
    border-color: #60a5fa;
    color: #ffffff;
}

QToolButton#TitlebarWindowButton,
QToolButton#TitlebarCloseButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    color: #e5e7eb;
    font-weight: 700;
    min-width: 34px;
    padding: 6px 8px;
}

QToolButton#TitlebarWindowButton:hover {
    background: #253142;
    border-color: #374151;
}

QToolButton#TitlebarCloseButton:hover {
    background: #dc2626;
    border-color: #ef4444;
    color: #ffffff;
}

QWidget#TitlebarTabsContent {
    background: #111827;
}
"""


class QtScopeWindow(PreviewQtScopeWindow):
    """Experimental launched window with control-page tabs in the title row."""

    def __init__(self, *args, **kwargs) -> None:
        self._titlebar_drag_position = None
        super().__init__(*args, **kwargs)
        self.setWindowTitle(TITLEBAR_WINDOW_TITLE)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

    def _build_ui(self) -> None:
        """Build a frameless shell with title, tabs, and window controls in one row."""
        central = QWidget(self)
        central.setObjectName("TitlebarTabsRoot")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)

        root.addWidget(self._build_titlebar_tabs_bar())

        content = QWidget(self)
        content.setObjectName("TitlebarTabsContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(18, 10, 18, 12)
        content_layout.setSpacing(10)
        root.addWidget(content, 1)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setObjectName("MainSplitter")
        self.main_splitter.setChildrenCollapsible(False)
        content_layout.addWidget(self.main_splitter, 1)

        preview_card = self._build_preview_card()
        preview_card.setMinimumWidth(PREVIEW_MIN_WIDTH)
        preview_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.main_splitter.addWidget(preview_card)

        right_panel = QWidget()
        right_panel.setObjectName("RightControlPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 10, 12, 12)
        right_layout.setSpacing(10)

        self.current_page_title = QLabel(CONTROL_TAB_TITLES[0])
        self.current_page_title.setObjectName("ControlPageTitle")
        right_layout.addWidget(self.current_page_title)

        self.control_stack = self._build_control_stack()
        self.control_stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        right_layout.addWidget(self.control_stack, 1)

        right_panel.setMinimumWidth(RIGHT_PANEL_MIN_WIDTH)
        right_panel.setMaximumWidth(RIGHT_PANEL_MAX_WIDTH)
        right_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.main_splitter.addWidget(right_panel)
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)
        self.main_splitter.setSizes([900, RIGHT_PANEL_DEFAULT_WIDTH])

        self.setStatusBar(QStatusBar())
        self.statusBar().setSizeGripEnabled(True)
        self._select_drawer_page(0)
        self._apply_preview_control_gutter()

    def _build_titlebar_tabs_bar(self) -> QWidget:
        """Build one top row containing title, page tabs, and window controls."""
        bar = QWidget(self)
        bar.setObjectName("TitlebarTabsBar")
        bar.setMinimumHeight(46)
        bar.setStyleSheet(TITLEBAR_TABS_QSS)
        self._install_titlebar_drag_handlers(bar)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(6)

        title = QLabel(TITLEBAR_WINDOW_TITLE)
        title.setObjectName("TitlebarWindowTitle")
        title.setMinimumWidth(155)
        title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._install_titlebar_drag_handlers(title)
        layout.addWidget(title)

        self.application_menu_buttons = QButtonGroup(self)
        self.application_menu_buttons.setExclusive(True)
        for index, title_text in enumerate(CONTROL_TAB_TITLES):
            button = QToolButton()
            button.setObjectName("TitlebarTabButton")
            button.setText(title_text)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setToolTip(f"Open {title_text} controls")
            button.clicked.connect(lambda checked=False, page=index: self._select_drawer_page(page))
            self.application_menu_buttons.addButton(button, index)
            layout.addWidget(button)

        layout.addStretch(1)
        layout.addWidget(self._window_control_button("—", self.showMinimized, "Minimize"))
        self.titlebar_maximize_button = self._window_control_button("□", self._toggle_maximized, "Maximize / restore")
        layout.addWidget(self.titlebar_maximize_button)
        layout.addWidget(self._window_control_button("×", self.close, "Close", close=True))
        return bar

    def _window_control_button(self, text: str, callback, tooltip: str, *, close: bool = False) -> QToolButton:
        button = QToolButton()
        button.setObjectName("TitlebarCloseButton" if close else "TitlebarWindowButton")
        button.setText(text)
        button.setToolTip(tooltip)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.clicked.connect(callback)
        return button

    def _install_titlebar_drag_handlers(self, widget: QWidget) -> None:
        widget.mousePressEvent = self._titlebar_mouse_press_event  # type: ignore[method-assign]
        widget.mouseMoveEvent = self._titlebar_mouse_move_event  # type: ignore[method-assign]
        widget.mouseReleaseEvent = self._titlebar_mouse_release_event  # type: ignore[method-assign]
        widget.mouseDoubleClickEvent = self._titlebar_mouse_double_click_event  # type: ignore[method-assign]

    @staticmethod
    def _event_global_position(event):
        if hasattr(event, "globalPosition"):
            return event.globalPosition().toPoint()
        return event.globalPos()

    def _titlebar_mouse_press_event(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._titlebar_drag_position = self._event_global_position(event) - self.frameGeometry().topLeft()
            event.accept()
            return
        event.ignore()

    def _titlebar_mouse_move_event(self, event) -> None:
        if self._titlebar_drag_position is None:
            event.ignore()
            return
        if event.buttons() & Qt.MouseButton.LeftButton:
            if self.isMaximized():
                self.showNormal()
                self._sync_maximize_button()
            self.move(self._event_global_position(event) - self._titlebar_drag_position)
            event.accept()
            return
        event.ignore()

    def _titlebar_mouse_release_event(self, event) -> None:
        self._titlebar_drag_position = None
        event.accept()

    def _titlebar_mouse_double_click_event(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximized()
            event.accept()
            return
        event.ignore()

    def _toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self._sync_maximize_button()

    def _sync_maximize_button(self) -> None:
        button = getattr(self, "titlebar_maximize_button", None)
        if button is not None:
            button.setText("❐" if self.isMaximized() else "□")


__all__ = ["QtScopeWindow", "TITLEBAR_TABS_QSS", "TITLEBAR_WINDOW_TITLE"]
