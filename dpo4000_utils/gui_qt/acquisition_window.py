"""PySide6 launched window with top menu navigation and Tektronix Acquisition setup."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .main_window import APP_TITLE, DEFAULT_DRAWER_WIDTH
from .ui_practice_window import SHORTCUTS, QtScopeWindow as TabbedQtScopeWindow

CONTROL_TAB_TITLES = (
    "Connection",
    "Channels",
    "Measurement",
    "Trigger",
    "Acquisition",
    "Settings",
    "Log",
)
PAGE_SHORTCUTS = (
    ("Ctrl+1", 0, "Connection"),
    ("Ctrl+2", 1, "Channels"),
    ("Ctrl+3", 2, "Measurement"),
    ("Ctrl+4", 3, "Trigger"),
    ("Ctrl+5", 4, "Acquisition"),
    ("Ctrl+6", 5, "Settings"),
    ("Ctrl+7", 6, "Log"),
)
ACQUISITION_MODES = (
    "SAMPLE",
    "PEAKDETECT",
    "HIRES",
    "AVERAGE",
    "ENVELOPE",
)
AVERAGE_COUNTS = (
    "2",
    "4",
    "8",
    "16",
    "32",
    "64",
    "128",
    "256",
    "512",
)
RECORD_LENGTHS = (
    "1000",
    "10000",
    "100000",
    "1000000",
    "10000000",
)
ACQUISITION_SETUP_QUERIES = {
    "mode": "ACQUIRE:MODE?",
    "average_count": "ACQUIRE:NUMAVG?",
    "record_length": "HORIZONTAL:RECORDLENGTH?",
}


class QtScopeWindow(TabbedQtScopeWindow):
    """Qt window with application-menu navigation and right-side control pages."""

    # ------------------------------------------------------------------
    # Top application menu layout
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        """Build preview plus right-side menu pages selected from a top menu row."""
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 12)
        root.setSpacing(10)
        self.setCentralWidget(central)

        root.addWidget(self._build_application_menu_bar())

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setObjectName("MainSplitter")
        root.addWidget(self.main_splitter, 1)

        preview_card = self._build_preview_card()
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

        right_panel.setMinimumWidth(420)
        right_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.main_splitter.addWidget(right_panel)
        self.main_splitter.setStretchFactor(0, 3)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([810, DEFAULT_DRAWER_WIDTH])

        self.setStatusBar(QStatusBar())
        self._select_drawer_page(0)

    def _build_application_menu_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("ApplicationMenuBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        title = QLabel(APP_TITLE)
        title.setObjectName("ApplicationMenuTitle")
        layout.addWidget(title)

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
        self.compact_mode_button = QToolButton()
        self.compact_mode_button.setObjectName("CompactModeButton")
        self.compact_mode_button.setCheckable(True)
        self.compact_mode_button.setChecked(True)
        self.compact_mode_button.setText("Compact")
        self.compact_mode_button.setToolTip("Hide advanced page sections")
        self.compact_mode_button.clicked.connect(self.toggle_compact_mode)
        layout.addWidget(self.compact_mode_button)
        return bar

    def _build_control_stack(self) -> QStackedWidget:
        stack = QStackedWidget()
        stack.setObjectName("RightControlStack")
        stack.addWidget(self._build_connection_tab())
        stack.addWidget(self._build_channels_tab())
        stack.addWidget(self._build_measurement_tab())
        stack.addWidget(self._build_trigger_tab())
        stack.addWidget(self._build_acquisition_tab())
        stack.addWidget(self._build_settings_tab())
        stack.addWidget(self._build_log_tab())
        return stack

    def _select_drawer_page(self, index: int) -> None:
        """Select the right-side page from top-menu buttons or Ctrl+number shortcuts."""
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

    def _build_control_tabs(self):  # pragma: no cover - retained only for older callers.
        """Compatibility shim: launched UI now uses top-menu buttons, not a tab widget."""
        return self._build_control_stack()

    def show_control_drawer(self) -> None:
        """Compatibility no-op: controls are always available through the top menu row."""
        self.statusBar().showMessage("Use the top menu row to open controls")

    def hide_control_drawer(self) -> None:
        """Compatibility no-op: the launched UI has no hideable drawer."""
        self.statusBar().showMessage("Control drawer removed; use the top menu row")

    def toggle_drawer_pin(self) -> None:
        """Compatibility no-op for older drawer shortcuts."""
        self.statusBar().showMessage("Control drawer removed; controls stay in the right panel")

    # ------------------------------------------------------------------
    # Trigger page: trigger plus manual acquisition actions
    # ------------------------------------------------------------------
    def _build_trigger_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_trigger_level_only_card())
        layout.addWidget(self._collapsible_section("Horizontal position", self._build_horizontal_position_card()))
        layout.addWidget(self._collapsible_section("Edge trigger setup", self._build_edge_trigger_card()))
        layout.addWidget(
            self._collapsible_section(
                "Manual acquisition buttons",
                self._build_acquisition_actions_card(),
            )
        )
        layout.addWidget(
            self._collapsible_section(
                "Image capture re-arm",
                self._build_image_rearm_card(),
            )
        )
        layout.addStretch(1)
        return self._wrap_scrollable_drawer_page(
            body,
            scroll_name="TriggerScrollArea",
            body_name="TriggerScrollBody",
        )

    def _build_trigger_level_only_card(self) -> QGroupBox:
        card = self._card("Trigger level")
        form = QFormLayout(card)
        self._prepare_form(form)

        self.trigger_channel = QComboBox()
        self.trigger_channel.addItems(["1", "2", "3", "4"])
        self.trigger_level = QLineEdit("1.0")
        self.trigger_set_source = QCheckBox("Set edge trigger source to selected channel")
        self.trigger_set_source.setChecked(True)
        self.trigger_readback = QLineEdit()
        self.trigger_readback.setReadOnly(True)

        form.addRow("Source", self.trigger_channel)
        form.addRow("Level V", self.trigger_level)
        form.addRow(self.trigger_set_source)
        form.addRow("Readback", self.trigger_readback)

        buttons = QHBoxLayout()
        buttons.addWidget(self._button("Read level", self.read_trigger_level))
        buttons.addWidget(self._accent_button("Set level", self.apply_trigger_level))
        form.addRow(buttons)
        return self._prepare_drawer_card(card)

    # ------------------------------------------------------------------
    # Acquisition page: Tektronix acquisition setup, not manual run controls
    # ------------------------------------------------------------------
    def _build_acquisition_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_acquisition_setup_card())
        layout.addStretch(1)
        return self._wrap_scrollable_drawer_page(
            body,
            scroll_name="AcquisitionScrollArea",
            body_name="AcquisitionScrollBody",
        )

    def _build_acquisition_setup_card(self) -> QGroupBox:
        card = self._card("Acquisition setup")
        form = QFormLayout(card)
        self._prepare_form(form)

        self.acquisition_mode = QComboBox()
        self.acquisition_mode.setEditable(True)
        self.acquisition_mode.addItems(ACQUISITION_MODES)
        self.acquisition_mode.setCurrentText("SAMPLE")

        self.acquisition_average_count = QComboBox()
        self.acquisition_average_count.setEditable(True)
        self.acquisition_average_count.addItems(AVERAGE_COUNTS)
        self.acquisition_average_count.setCurrentText("16")
        self.acquisition_average_count.setToolTip("Only active when acquisition mode is AVERAGE.")

        self.acquisition_record_length = QComboBox()
        self.acquisition_record_length.setEditable(True)
        self.acquisition_record_length.addItems(RECORD_LENGTHS)

        form.addRow("Mode", self.acquisition_mode)
        form.addRow("Average count", self.acquisition_average_count)
        form.addRow("Record length", self.acquisition_record_length)

        hint = QLabel(
            "Tektronix acquisition setup: HIRES is high-resolution mode; "
            "AVERAGE enables ACQUIRE:NUMAVG; record length uses HORIZONTAL:RECORDLENGTH."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        form.addRow(hint)

        buttons = QHBoxLayout()
        buttons.addWidget(self._button("Read acquisition setup", self.read_acquisition_setup))
        buttons.addWidget(self._accent_button("Apply acquisition setup", self.apply_acquisition_setup))
        form.addRow(buttons)

        self.acquisition_mode.currentTextChanged.connect(self._update_average_count_enabled)
        self._update_average_count_enabled()
        return self._prepare_drawer_card(card)

    def _build_acquisition_actions_card(self) -> QGroupBox:
        card = self._card("Manual acquisition buttons")
        grid = QGridLayout(card)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        grid.addWidget(self._button("Run", self.run_acquisition), 0, 0)
        grid.addWidget(self._button("Stop", self.stop_acquisition), 0, 1)
        grid.addWidget(self._button("Single", self.single_acquisition), 0, 2)
        grid.addWidget(self._button("Continuous", self.continuous_acquisition), 1, 0)
        grid.addWidget(self._accent_button("Force trigger", self.force_trigger), 1, 1, 1, 2)
        return self._prepare_drawer_card(card)

    def _is_average_mode(self) -> bool:
        return self.acquisition_mode.currentText().strip().upper() == "AVERAGE"

    def _update_average_count_enabled(self) -> None:
        enabled = self._is_average_mode()
        self.acquisition_average_count.setEnabled(enabled)
        self.acquisition_average_count.setToolTip(
            "Active because acquisition mode is AVERAGE."
            if enabled
            else "Disabled because acquisition mode is not AVERAGE; ACQUIRE:NUMAVG is skipped."
        )

    def read_acquisition_setup(self) -> None:
        def action(scope):
            instrument = getattr(scope, "scope", None)
            if instrument is None:
                raise ConnectionError("Oscilloscope is not connected.")
            return {
                name: self._query_optional(instrument, query)
                for name, query in ACQUISITION_SETUP_QUERIES.items()
            }

        result = self._run_action("Reading acquisition setup", action)
        if isinstance(result, dict):
            self._set_combo_text(self.acquisition_mode, result.get("mode", ""))
            self._set_combo_text(self.acquisition_average_count, result.get("average_count", ""))
            self._set_combo_text(self.acquisition_record_length, result.get("record_length", ""))
            self._update_average_count_enabled()
            mode = self.acquisition_mode.currentText().strip() or "Unknown"
            length = self.acquisition_record_length.currentText().strip() or "Unknown length"
            self._acquisition_state = f"{mode}, {length} pts"
            self._update_status_strip()

    def apply_acquisition_setup(self) -> None:
        mode = self.acquisition_mode.currentText().strip().upper()
        average_count = self.acquisition_average_count.currentText().strip()
        record_length = self.acquisition_record_length.currentText().strip()
        use_average_count = mode == "AVERAGE"

        def action(scope):
            instrument = getattr(scope, "scope", None)
            if instrument is None:
                raise ConnectionError("Oscilloscope is not connected.")
            if mode:
                instrument.write(f"ACQUIRE:MODE {mode}")
            if use_average_count:
                self._write_if_text(instrument, "ACQUIRE:NUMAVG", average_count)
            self._write_if_text(instrument, "HORIZONTAL:RECORDLENGTH", record_length)
            readback = {
                name: self._query_optional(instrument, query)
                for name, query in ACQUISITION_SETUP_QUERIES.items()
            }
            avg_text = readback.get("average_count", average_count) if use_average_count else "skipped"
            return (
                "Acquisition setup applied: "
                f"mode={readback.get('mode', mode)}, "
                f"average_count={avg_text}, "
                f"record_length={readback.get('record_length', record_length)}"
            )

        result = self._run_action("Applying acquisition setup", action)
        if result is not None:
            length = record_length or self.acquisition_record_length.currentText().strip() or "Unknown length"
            self._acquisition_state = f"{mode or 'Unknown'}, {length} pts"
            self._update_average_count_enabled()
            self._update_status_strip()

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------
    def _install_global_shortcuts(self) -> None:
        for key, label, method_name, requires_scope in SHORTCUTS:
            method = getattr(self, method_name)
            self._make_shortcut(
                key,
                lambda checked=False, callback=method, shortcut_label=label, guarded=requires_scope: (
                    self._guarded_scope_call(callback, shortcut_label) if guarded else callback()
                ),
            )
        self._make_shortcut("Ctrl+L", self._focus_resource_field)
        for key, page, _title in PAGE_SHORTCUTS:
            self._make_shortcut(key, lambda checked=False, index=page: self._select_drawer_page(index))


__all__ = [
    "ACQUISITION_MODES",
    "ACQUISITION_SETUP_QUERIES",
    "AVERAGE_COUNTS",
    "CONTROL_TAB_TITLES",
    "PAGE_SHORTCUTS",
    "RECORD_LENGTHS",
    "QtScopeWindow",
]
