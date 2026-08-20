"""PySide6 launched window with a dedicated Acquisition tab."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
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


class QtScopeWindow(TabbedQtScopeWindow):
    """Tabbed Qt window with acquisition controls split out of Trigger."""

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
    # Trigger tab: trigger-only controls
    # ------------------------------------------------------------------
    def _build_trigger_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_trigger_level_only_card())
        layout.addWidget(self._collapsible_section("Horizontal position", self._build_horizontal_position_card()))
        layout.addWidget(self._collapsible_section("Edge trigger setup", self._build_edge_trigger_card()))
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
    # Acquisition tab
    # ------------------------------------------------------------------
    def _build_acquisition_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_acquisition_actions_card())
        layout.addWidget(self._build_image_rearm_card())
        layout.addStretch(1)
        return self._wrap_scrollable_drawer_page(
            body,
            scroll_name="AcquisitionScrollArea",
            body_name="AcquisitionScrollBody",
        )

    def _build_acquisition_actions_card(self) -> QGroupBox:
        card = self._card("Acquisition controls")
        grid = QGridLayout(card)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        grid.addWidget(self._button("Run", self.run_acquisition), 0, 0)
        grid.addWidget(self._button("Stop", self.stop_acquisition), 0, 1)
        grid.addWidget(self._button("Single", self.single_acquisition), 0, 2)
        grid.addWidget(self._button("Continuous", self.continuous_acquisition), 1, 0)
        grid.addWidget(self._accent_button("Force trigger", self.force_trigger), 1, 1, 1, 2)
        return self._prepare_drawer_card(card)

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


__all__ = ["CONTROL_TAB_TITLES", "PAGE_SHORTCUTS", "QtScopeWindow"]
