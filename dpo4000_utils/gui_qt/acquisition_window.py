"""PySide6 launched window with a dedicated Tektronix Acquisition setup tab."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

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
    """Tabbed Qt window with Tektronix acquisition setup split out of Trigger."""

    def _build_control_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setObjectName("ControlTabs")
        tabs.setDocumentMode(True)
        tabs.setTabPosition(QTabWidget.TabPosition.North)
        tabs.addTab(self._build_connection_tab(), CONTROL_TAB_TITLES[0])
        tabs.addTab(self._build_channels_tab(), CONTROL_TAB_TITLES[1])
        tabs.addTab(self._build_measurement_tab(), CONTROL_TAB_TITLES[2])
        tabs.addTab(self._build_trigger_tab(), CONTROL_TAB_TITLES[3])
        tabs.addTab(self._build_acquisition_tab(), CONTROL_TAB_TITLES[4])
        tabs.addTab(self._build_settings_tab(), CONTROL_TAB_TITLES[5])
        tabs.addTab(self._build_log_tab(), CONTROL_TAB_TITLES[6])
        return tabs

    # ------------------------------------------------------------------
    # Trigger tab: trigger plus manual acquisition actions
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
    # Acquisition tab: Tektronix acquisition setup, not manual run controls
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
