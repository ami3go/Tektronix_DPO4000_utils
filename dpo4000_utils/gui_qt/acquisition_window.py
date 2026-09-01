"""PySide6 launched window with top menu navigation and Tektronix Acquisition setup."""

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
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .main_window import APP_TITLE, DEFAULT_DRAWER_WIDTH
from .ui_practice_window import SHORTCUTS
from .ui_practice_window import QtScopeWindow as TabbedQtScopeWindow

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
    "1k",
    "10k",
    "100k",
    "1M",
    "10M",
)
RECORD_LENGTH_VALUE_BY_LABEL = {
    "1K": "1000",
    "10K": "10000",
    "100K": "100000",
    "1M": "1000000",
    "10M": "10000000",
}
RECORD_LENGTH_LABEL_BY_VALUE = {
    value: label
    for label, value in (
        ("1k", "1000"),
        ("10k", "10000"),
        ("100k", "100000"),
        ("1M", "1000000"),
        ("10M", "10000000"),
    )
}
ACQUISITION_SETUP_QUERIES = {
    "mode": "ACQUIRE:MODE?",
    "average_count": "ACQUIRE:NUMAVG?",
    "record_length": "HORIZONTAL:RECORDLENGTH?",
}
PREVIEW_MIN_WIDTH = 480
RIGHT_PANEL_MIN_WIDTH = 400
RIGHT_PANEL_DEFAULT_WIDTH = DEFAULT_DRAWER_WIDTH
RIGHT_PANEL_MAX_WIDTH = 620


class QtScopeWindow(TabbedQtScopeWindow):
    """Qt window with application-menu navigation and right-side control pages."""

    def _apply_compact_mode(self) -> None:
        """Force the launched UI to use advanced mode only."""
        self.compact_mode = False
        for widget in getattr(self, "_advanced_widgets", []):
            widget.setVisible(True)

    def _register_advanced_widget(self, widget: QWidget) -> QWidget:
        """Keep advanced sections visible in the launched top-menu UI."""
        self._advanced_widgets.append(widget)
        widget.setVisible(True)
        return widget

    def _collapsible_section(
        self, title: str, content: QWidget, *, expanded: bool = True
    ) -> QWidget:
        """Open advanced sections by default; no Compact/Advanced toggle is shown."""
        return super()._collapsible_section(title, content, expanded=True)

    def toggle_compact_mode(self) -> None:
        """Compatibility no-op: advanced mode is the only launched mode."""
        self._apply_compact_mode()
        self.statusBar().showMessage("Advanced controls are always visible")

    # ------------------------------------------------------------------
    # Preview toolbar
    # ------------------------------------------------------------------
    def _build_quick_control_bar(self) -> QWidget:
        """Keep preview/export and duplicate trigger controls near the preview."""
        toolbar = QWidget()
        toolbar.setObjectName("QuickControlBar")
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        quick_actions = (
            ("IDN", self.test_connection, False),
            ("Capture", self.capture_preview, False),
            ("Copy", self.copy_preview, False),
            ("PNG", self.save_png_image, False),
            ("CSV", self.save_csv, False),
        )
        for text, callback, accent in quick_actions:
            layout.addWidget(self._quick_button(text, callback, accent=accent))

        layout.addSpacing(10)
        trigger_actions = (
            ("Run", self.run_acquisition, False),
            ("Stop", self.stop_acquisition, False),
            ("Single", self.single_acquisition, False),
            ("Continuous", self.continuous_acquisition, False),
            ("Force", self.force_trigger, True),
        )
        for text, callback, accent in trigger_actions:
            layout.addWidget(self._quick_button(text, callback, accent=accent))

        layout.addStretch(1)
        return toolbar

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
        self.main_splitter.setChildrenCollapsible(False)
        root.addWidget(self.main_splitter, 1)

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
    # Trigger page: trigger plus always-visible manual acquisition actions
    # ------------------------------------------------------------------
    def _build_trigger_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_trigger_acquisition_toolbar())
        layout.addWidget(self._build_trigger_level_only_card())
        layout.addWidget(
            self._collapsible_section("Horizontal position", self._build_horizontal_position_card())
        )
        layout.addWidget(
            self._collapsible_section("Edge trigger setup", self._build_edge_trigger_card())
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

    def _build_trigger_acquisition_toolbar(self) -> QWidget:
        toolbar = QWidget()
        toolbar.setObjectName("TriggerAcquisitionToolbar")
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)
        actions = (
            ("Run", self.run_acquisition, False, "F6 · Start acquisition"),
            ("Stop", self.stop_acquisition, False, "F7 · Stop acquisition"),
            ("Single", self.single_acquisition, False, "F8 · Start single acquisition"),
            ("Continuous", self.continuous_acquisition, False, "Start continuous acquisition"),
            ("Force", self.force_trigger, True, "Force one trigger event"),
        )
        for text, callback, accent, tooltip in actions:
            button = self._accent_button(text, callback) if accent else self._button(text, callback)
            button.setToolTip(tooltip)
            layout.addWidget(button)
        layout.addStretch(1)
        return toolbar

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
        self.acquisition_record_length.setToolTip(
            "Friendly labels are converted to point counts for HORIZONTAL:RECORDLENGTH."
        )

        form.addRow("Mode", self.acquisition_mode)
        form.addRow("Average count", self.acquisition_average_count)
        form.addRow("Record length", self.acquisition_record_length)

        hint = QLabel(
            "Tektronix acquisition setup: HIRES is high-resolution mode; "
            "AVERAGE enables ACQUIRE:NUMAVG; record length labels 1k, 10k, 100k, 1M, 10M "
            "are sent as numeric HORIZONTAL:RECORDLENGTH point counts."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        form.addRow(hint)

        buttons = QHBoxLayout()
        buttons.addWidget(self._button("Read acquisition setup", self.read_acquisition_setup))
        buttons.addWidget(
            self._accent_button("Apply acquisition setup", self.apply_acquisition_setup)
        )
        form.addRow(buttons)

        self.acquisition_mode.currentTextChanged.connect(self._update_average_count_enabled)
        self._update_average_count_enabled()
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

    @staticmethod
    def _normalise_record_length_points(text: str) -> str:
        value = str(text).strip()
        if not value:
            return ""
        label_key = value.upper().replace(" ", "")
        if label_key in RECORD_LENGTH_VALUE_BY_LABEL:
            return RECORD_LENGTH_VALUE_BY_LABEL[label_key]
        try:
            return str(int(float(value)))
        except ValueError:
            return value

    @classmethod
    def _record_length_label(cls, text: str) -> str:
        points = cls._normalise_record_length_points(text)
        return RECORD_LENGTH_LABEL_BY_VALUE.get(points, points)

    def _selected_record_length_points(self) -> str:
        return self._normalise_record_length_points(self.acquisition_record_length.currentText())

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
            self._set_combo_text(
                self.acquisition_record_length,
                self._record_length_label(result.get("record_length", "")),
            )
            self._update_average_count_enabled()
            mode = self.acquisition_mode.currentText().strip() or "Unknown"
            length = self.acquisition_record_length.currentText().strip() or "Unknown length"
            self._acquisition_state = f"{mode}, {length} pts"
            self._update_status_strip()

    def apply_acquisition_setup(self) -> None:
        mode = self.acquisition_mode.currentText().strip().upper()
        average_count = self.acquisition_average_count.currentText().strip()
        record_length = self._selected_record_length_points()
        record_length_label = self._record_length_label(record_length)
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
            avg_text = (
                readback.get("average_count", average_count) if use_average_count else "skipped"
            )
            readback_length = readback.get("record_length", record_length)
            readback_label = self._record_length_label(readback_length)
            return (
                "Acquisition setup applied: "
                f"mode={readback.get('mode', mode)}, "
                f"average_count={avg_text}, "
                f"record_length={readback_label} "
                f"({self._normalise_record_length_points(readback_length)})"
            )

        result = self._run_action("Applying acquisition setup", action)
        if result is not None:
            self._set_combo_text(self.acquisition_record_length, record_length_label)
            self._acquisition_state = (
                f"{mode or 'Unknown'}, {record_length_label or 'Unknown length'} pts"
            )
            self._update_average_count_enabled()
            self._update_status_strip()

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------
    def _install_global_shortcuts(self) -> None:
        for key, label, method_name, requires_scope in SHORTCUTS:
            method = getattr(self, method_name)
            self._make_shortcut(
                key, self._shortcut_activation(method, label, guarded=requires_scope)
            )
        self._make_shortcut("Ctrl+L", self._focus_resource_field)
        for key, page, _title in PAGE_SHORTCUTS:
            self._make_shortcut(
                key, lambda checked=False, index=page: self._select_drawer_page(index)
            )


__all__ = [
    "ACQUISITION_MODES",
    "ACQUISITION_SETUP_QUERIES",
    "AVERAGE_COUNTS",
    "CONTROL_TAB_TITLES",
    "PAGE_SHORTCUTS",
    "RECORD_LENGTH_LABEL_BY_VALUE",
    "RECORD_LENGTH_VALUE_BY_LABEL",
    "RECORD_LENGTHS",
    "QtScopeWindow",
]
