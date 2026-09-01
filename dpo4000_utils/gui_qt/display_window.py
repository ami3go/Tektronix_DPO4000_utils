"""Stable PySide6 window with dedicated File and Display pages.

The launched UI keeps file/output actions under a File page and moves front-panel
scope display controls into their own Display top-menu page.
"""

from __future__ import annotations

from pathlib import Path

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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .stable_window import TRIGGER_PAGE_INDEX
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
DISPLAY_PERSISTENCE_VALUES = (
    "AUTO",
    "MINIMUM",
    "INFINITE",
    "CLEAR",
    "0.5",
    "1",
    "2",
    "5",
    "10",
)
DISPLAY_SETUP_QUERIES = {
    "backlight": "DISPLAY:INTENSITY:BACKLIGHT?",
    "waveform": "DISPLAY:INTENSITY:WAVEFORM?",
    "graticule": "DISPLAY:INTENSITY:GRATICULE?",
    "persistence": "DISPLAY:PERSISTENCE?",
    "message_text": "MESSAGE:SHOW?",
    "message_state": "MESSAGE:STATE?",
}
DISPLAY_SCOPE_ACTIONS = {
    "read_display_settings",
    "apply_display_settings",
    "clear_display_message",
}


class QtScopeWindow(StableQtScopeWindow):
    """Stable launched Qt window with a dedicated Display controls page."""

    def _control_page_builder_names(self) -> tuple[str, ...]:
        """File and Display are separate pages here, so this layout has eight."""
        return CONTROL_PAGE_BUILDERS

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

    def _select_drawer_page(self, index: int) -> None:
        """Select the requested top-menu page using the Display-aware page list."""
        self._ensure_control_page_built(index)
        stack = getattr(self, "control_stack", None)
        if stack is None or index < 0 or index >= stack.count():
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

    # ------------------------------------------------------------------
    # Lazy-page-safe widget accessors
    # ------------------------------------------------------------------
    # Quick actions can run before the page owning their widgets has been built,
    # so the build guard lives on the accessor rather than on each action. Guarding
    # the action instead is not safe here: later layers override the actions and a
    # missed super() call silently drops the guard.
    def _build_output_path(self, kind: str) -> Path:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        return super()._build_output_path(kind)

    def _configured_output_folder(self, *, create: bool = True) -> Path:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        return super()._configured_output_folder(create=create)

    def _rearm_after_image_enabled(self) -> bool:
        self._ensure_control_page_built(TRIGGER_PAGE_INDEX)
        return super()._rearm_after_image_enabled()

    def _trigger_channel_or_none(self) -> int | None:
        self._ensure_control_page_built(TRIGGER_PAGE_INDEX)
        return super()._trigger_channel_or_none()

    def _install_global_shortcuts(self) -> None:
        """Install global action shortcuts plus Ctrl+1..8 page navigation."""
        for key, label, method_name, requires_scope in SHORTCUTS:
            method = getattr(self, method_name)
            self._make_shortcut(
                key, self._shortcut_activation(method, label, guarded=requires_scope)
            )
        self._make_shortcut("Ctrl+L", self._focus_resource_field)
        for key, page, _title in DISPLAY_PAGE_SHORTCUTS:
            self._make_shortcut(
                key, lambda checked=False, index=page: self._select_drawer_page(index)
            )

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
        self.display_backlight.setToolTip("DISPLAY:INTENSITY:BACKLIGHT, usually 0..100.")
        self.display_waveform_intensity = QLineEdit("")
        self.display_waveform_intensity.setToolTip("Optional DISPLAY:INTENSITY:WAVEFORM value.")
        self.display_graticule_intensity = QLineEdit("")
        self.display_graticule_intensity.setToolTip("Optional DISPLAY:INTENSITY:GRATICULE value.")

        self.display_persistence = QComboBox()
        self.display_persistence.setEditable(True)
        self.display_persistence.addItems(DISPLAY_PERSISTENCE_VALUES)
        self.display_persistence.setToolTip(
            "DISPLAY:PERSISTENCE accepts AUTO, MINIMUM, INFINITE, CLEAR, or a time value."
        )

        self.display_message_text = QLineEdit("")
        self.display_message_text.setMaxLength(120)
        self.display_message_text.setToolTip(
            "MESSAGE:SHOW text added as a message box on the scope screen."
        )
        self.display_message_state = QCheckBox("Show text box on scope screen")

        form.addRow("Contrast / backlight %", self.display_backlight)
        form.addRow("Waveform intensity", self.display_waveform_intensity)
        form.addRow("Graticule intensity", self.display_graticule_intensity)
        form.addRow("Persistence", self.display_persistence)
        form.addRow("Screen text", self.display_message_text)
        form.addRow(self.display_message_state)

        hint = QLabel(
            "Backlight/waveform/graticule values map to DISPLAY:INTENSITY commands. "
            "Persistence maps to DISPLAY:PERSISTENCE. Screen text uses MESSAGE:SHOW, "
            "MESSAGE:STATE, and MESSAGE:CLEAR. Some firmware may reject unsupported values."
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
    # SCPI actions
    # ------------------------------------------------------------------
    @staticmethod
    def _quote_scpi_string(value: str) -> str:
        """Quote screen message text for SCPI while keeping it single-line and safe."""
        clean = " ".join(str(value).replace('"', "'").splitlines()).strip()
        return f'"{clean}"'

    def read_display_settings(self) -> None:
        def action(scope) -> dict[str, str]:
            instrument = getattr(scope, "scope", None)
            if instrument is None:
                raise ConnectionError("Oscilloscope is not connected.")
            return {
                name: self._query_optional(instrument, query)
                for name, query in DISPLAY_SETUP_QUERIES.items()
            }

        result = self._run_action("Reading display settings", action)
        if isinstance(result, dict):
            self.display_backlight.setText(result.get("backlight", ""))
            self.display_waveform_intensity.setText(result.get("waveform", ""))
            self.display_graticule_intensity.setText(result.get("graticule", ""))
            self._set_combo_text(self.display_persistence, result.get("persistence", ""))
            self.display_message_text.setText(result.get("message_text", ""))
            self.display_message_state.setChecked(
                self._bool_from_scope_response(result.get("message_state", "0"))
            )

    def apply_display_settings(self) -> None:
        backlight = self.display_backlight.text()
        waveform = self.display_waveform_intensity.text()
        graticule = self.display_graticule_intensity.text()
        persistence = self.display_persistence.currentText().strip().upper()
        message_text = self.display_message_text.text().strip()
        message_state = self.display_message_state.isChecked()

        def action(scope) -> str:
            instrument = getattr(scope, "scope", None)
            if instrument is None:
                raise ConnectionError("Oscilloscope is not connected.")
            self._write_if_text(instrument, "DISPLAY:INTENSITY:BACKLIGHT", backlight)
            self._write_if_text(instrument, "DISPLAY:INTENSITY:WAVEFORM", waveform)
            self._write_if_text(instrument, "DISPLAY:INTENSITY:GRATICULE", graticule)
            self._write_if_text(instrument, "DISPLAY:PERSISTENCE", persistence)
            if message_text:
                instrument.write(f"MESSAGE:SHOW {self._quote_scpi_string(message_text)}")
            instrument.write(f"MESSAGE:STATE {'ON' if message_state else 'OFF'}")
            return "Display settings applied"

        self._run_action("Applying display settings", action)

    def clear_display_message(self) -> None:
        def action(scope) -> str:
            instrument = getattr(scope, "scope", None)
            if instrument is None:
                raise ConnectionError("Oscilloscope is not connected.")
            instrument.write("MESSAGE:CLEAR")
            instrument.write("MESSAGE:STATE OFF")
            return "Screen text cleared"

        result = self._run_action("Clearing display screen text", action)
        if result is not None:
            self.display_message_text.clear()
            self.display_message_state.setChecked(False)


__all__ = [
    "CONTROL_PAGE_BUILDERS",
    "CONTROL_TAB_TITLES",
    "DISPLAY_PAGE_INDEX",
    "DISPLAY_PAGE_SHORTCUTS",
    "DISPLAY_PERSISTENCE_VALUES",
    "DISPLAY_SCOPE_ACTIONS",
    "DISPLAY_SETUP_QUERIES",
    "FILE_PAGE_INDEX",
    "LOG_PAGE_INDEX",
    "QtScopeWindow",
]
