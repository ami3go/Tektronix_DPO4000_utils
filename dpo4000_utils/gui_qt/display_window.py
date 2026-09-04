"""Stable PySide6 window with dedicated File and Display pages.

The launched UI keeps file/output actions under a File page and moves front-panel
scope display controls into their own Display top-menu page.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..control import DISPLAY_PERSISTENCE_VALUES, DisplayConfig, bool_from_scope_response
from .stable_window import QtScopeWindow as StableQtScopeWindow
from .ui_practice_window import SHORTCUTS

CONTROL_TAB_TITLES = (
    "Connection",
    "Channels",
    "Measurement",
    "Trigger",
    "Acquisition",
    "File",
    "Display",
    "Log",
)
CONTROL_PAGE_BUILDERS = (
    "_build_connection_tab",
    "_build_channels_tab",
    "_build_measurement_tab",
    "_build_trigger_tab",
    "_build_acquisition_tab",
    "_build_file_tab",
    "_build_display_tab",
    "_build_log_tab",
)
DISPLAY_PAGE_SHORTCUTS = (
    ("Ctrl+1", 0, "Connection"),
    ("Ctrl+2", 1, "Channels"),
    ("Ctrl+3", 2, "Measurement"),
    ("Ctrl+4", 3, "Trigger"),
    ("Ctrl+5", 4, "Acquisition"),
    ("Ctrl+6", 5, "File"),
    ("Ctrl+7", 6, "Display"),
    ("Ctrl+8", 7, "Log"),
)
FILE_PAGE_INDEX = 5
DISPLAY_PAGE_INDEX = 6
LOG_PAGE_INDEX = 7
DISPLAY_SCOPE_ACTIONS = {
    "read_display_settings",
    "apply_display_settings",
    "clear_display_message",
}


class QtScopeWindow(StableQtScopeWindow):
    """Stable launched Qt window with a dedicated Display controls page."""

    def _callback_requires_scope(self, callback) -> bool:
        """Make display-setting buttons follow the same IDN-first safety gate."""
        if getattr(callback, "__name__", "") in DISPLAY_SCOPE_ACTIONS:
            return True
        return super()._callback_requires_scope(callback)

    # ------------------------------------------------------------------
    # Top menu and lazy page construction
    # ------------------------------------------------------------------
    def _build_application_menu_bar(self) -> QWidget:
        """Build the top menu with File and Display as separate pages."""
        bar = QWidget()
        bar.setObjectName("ApplicationMenuBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        self.application_menu_buttons = QButtonGroup(self)
        self.application_menu_buttons.setExclusive(True)
        for index, title_text in enumerate(CONTROL_TAB_TITLES):
            button = QToolButton()
            button.setObjectName("ApplicationMenuButton")
            button.setText(title_text)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setToolTip(f"Open {title_text} controls")
            button.clicked.connect(lambda checked=False, page=index: self._select_drawer_page(page))
            self.application_menu_buttons.addButton(button, index)
            layout.addWidget(button)

        layout.addStretch(1)
        return bar

    def _build_control_stack(self) -> QStackedWidget:
        """Create placeholder pages and build real File/Display pages lazily."""
        stack = QStackedWidget()
        stack.setObjectName("RightControlStack")
        self._lazy_control_pages_built = [False for _ in CONTROL_PAGE_BUILDERS]
        self._lazy_control_pages_preferences_applied = [False for _ in CONTROL_PAGE_BUILDERS]
        for index, _builder_name in enumerate(CONTROL_PAGE_BUILDERS):
            placeholder = QWidget()
            placeholder.setObjectName(f"LazyControlPagePlaceholder{index}")
            stack.addWidget(placeholder)
        return stack

    def _select_drawer_page(self, index: int) -> None:
        """Select the requested top-menu page using the Display-aware page list."""
        self._ensure_control_page_built(index)
        stack = getattr(self, "control_stack", None)
        if stack is none or index < 0 or index >= stack.count():
            return
        stack.setCurrentIndex(index)
        title = CONTROL_TAB_TITLES[index]
        page_title = getattr(self, "current_page_title", None)
        if page_title is not None:
            page_title.setText(title)
        button_group = getattr(self, "application_menu_buttons", None)
        if button_group is not None:
            button = button_group.button(index)
            if button is not None:
                button.setChecked(True)
        self.statusBar().showMessage(f"Opened {title} controls")

    def _ensure_control_page_built(self, index: int) -> None:
        """Build a top-menu page only once, using the File/Display page map."""
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

        self._apply_preferences_to_control_page(index)
        update_controls = getattr(self, "_update_scope_control_enabled", None)
        if callable(update_controls):
            update_controls()

    def _install_global_shortcuts(self) -> None:
        """Install global action shortcuts plus Ctrl+1..8 page navigation."""
        for key, label, method_name, requires_scope in SHORTCUTS:
            method = getattr(self, method_name)
            self._make_shortcut(
                key,
                lambda checked=False, callback=method, shortcut_label=label, guarded=requires_scope: (
                    self._guarded_scope_call(callback, shortcut_label) if guarded else callback()
                ),
            )
        self._make_shortcut("Ctrl+L", self._focus_resource_field)
        for key, page, _title in DISPLAY_PAGE_SHORTCUTS:
            self._make_shortcut(key, lambda checked=False, index=page: self._select_drawer_page(index))

    # ------------------------------------------------------------------
    # Page builders
    # ------------------------------------------------------------------
    def _build_file_tab(self) -> QWidget:
        """Build the renamed File page with output and setup file controls."""
        return super()._build_settings_tab()

    def _build_display_tab(self) -> QWidget:
        """Build the dedicated display, persistence, and scope-screen text page."""
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)
        layout.addWidget(self._build_display_settings_card())
        layout.addStretch(1)
        return self._wrap_scrollable_drawer_page(
            body,
            scroll_name="DisplayScrollArea",
            body_name="DisplayScrollBody",
        )

    def _build_display_settings_card(self) -> QGroupBox:
        card = self._card("Display, persistence, and screen text")
        form = QFormLayout(card)
        self._prepare_form(form)

        self.display_backlight = QLineEdit("100")
        self.display_backlight.setToolTip("Display backlight intensity, usually 0..100.")
        self.display_waveform_intensity = QLineEdit("")
        self.display_waveform_intensity.setToolTip("Optional waveform display intensity.")
        self.display_graticule_intensity = QLineEdit("")
        self.display_graticule_intensity.setToolTip("Optional graticule display intensity.")

        self.display_persistence = QComboBox()
        self.display_persistence.setEditable(True)
        self.display_persistence.addItems(DISPLAY_PERSISTENCE_VALUES)
        self.display_persistence.setToolTip(
            "Persistence accepts AUTO, MINIMUM, INFINITE, CLEAR, or a time value."
        )

        self.display_message_text = QLineEdit("")
        self.display_message_text.setMaxLength(120)
        self.display_message_text.setToolTip("Optional message box text shown on the scope screen.")
        self.display_message_state = QCheckBox("Show text box on scope screen")

        form.addRow("Contrast / backlight %", self.display_backlight)
        form.addRow("Waveform intensity", self.display_waveform_intensity)
        form.addRow("Graticule intensity", self.display_graticule_intensity)
        form.addRow("Persistence", self.display_persistence)
        form.addRow("Screen text", self.display_message_text)
        form.addRow(self.display_message_state)

        hint = QLabel(
            "Display controls are applied through the public DPO4000 driver API. "
            "Unsupported values may be rejected by older instrument firmware."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        form.addRow(hint)

        buttons = QHBoxLayout()
        read_button = self._button("Read display", self.read_display_settings)
        apply_button = self._accent_button("Apply display", self.apply_display_settings)
        clear_button = self._button("Clear text", self.clear_display_message)
        for button in (read_button, apply_button, clear_button):
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            buttons.addWidget(button)
        form.addRow(buttons)
        return self._prepare_drawer_card(card)

    # ------------------------------------------------------------------
    # Public-driver actions
    # ------------------------------------------------------------------
    def read_display_settings(self) -> None:
        result = self._run_action(
            "Reading display settings",
            lambda scope: scope.get_display_settings(),
        )
        if isinstance(result, dict):
            self.display_backlight.setText(result.get("backlight", ""))
            self.display_waveform_intensity.setText(result.get("waveform", ""))
            self.display_graticule_intensity.setText(result.get("graticule", ""))
            self._set_combo_text(self.display_persistence, result.get("persistence", ""))
            self.display_message_text.setText(result.get("message_text", ""))
            self.display_message_state.setChecked(
                bool_from_scope_response(result.get("message_state", "0"))
            )

    def apply_display_settings(self) -> None:
        config = DisplayConfig(
            backlight=self.display_backlight.text().strip() or None,
            waveform=self.display_waveform_intensity.text().strip() or None,
            graticule=self.display_graticule_intensity.text().strip() or None,
            persistence=self.display_persistence.currentText().strip() or None,
            message_text=self.display_message_text.text().strip() or None,
            message_state=self.display_message_state.isChecked(),
        )
        self._run_action(
            "Applying display settings",
            lambda scope: scope.apply_display_settings(config),
        )

    def clear_display_message(self) -> None:
        result = self._run_action(
            "Clearing display screen text",
            lambda scope: scope.clear_display_message(),
        )
        if result is not None or getattr(self, "_connection_ok", False):
            self.display_message_text.clear()
            self.display_message_state.setChecked(False)


__all__ = [
    "CONTROL_PAGE_BUILDERS",
    "CONTROL_TAB_TITLES",
    "DISPLAY_PAGE_INDEX",
    "DISPLAY_PAGE_SHORTCUTS",
    "DISPLAY_PERSISTENCE_VALUES",
    "DISPLAY_SCOPE_ACTIONS",
    "FILE_PAGE_INDEX",
    "LOG_PAGE_INDEX",
    "QtScopeWindow",
]
