"""Experimental PySide6 main window for the DPO4000 utility.

The Qt GUI is intentionally kept beside the existing Tkinter GUI while the
project compares modern UI options.  This module ports the user-facing actions
from the Tk ``main`` GUI to PySide6 while continuing to call the same shared
DPO4000 driver/helper modules.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..channels import validate_channel
from ..connection import (
    build_tcpip_instr_resource,
    build_tcpip_socket_resource,
    list_visa_resources,
    visaResourceAddr,
)
from ..control import (
    MEASUREMENT_SLOTS,
    MEASUREMENT_SOURCES,
    MEASUREMENT_TYPES_BY_GROUP,
    TRIGGER_COUPLINGS,
    TRIGGER_MODES,
    TRIGGER_SLOPES,
    TRIGGER_SOURCES,
    MeasurementConfig,
)
from ..gui.config import FileNaming, build_output_path, resolve_output_folder
from ..gui.preferences import GuiPreferences, load_preferences, save_preferences
from ..hardcopy import save_screen_png
from ..instrument import DPO4054
from ..settings import apply_scope_settings_file
from ..waveform import save_enabled_channels_to_single_csv

APP_TITLE = "Tektronix DPO4000 Utilities — Qt preview"
DRAWER_PAGE_TITLES = ("Connection", "Channels", "Measurement", "Trigger", "Settings", "Log")
DEFAULT_DRAWER_WIDTH = 470
DEFAULT_RESTORE_TIMEOUT_MS = 60_000


class QtScopeWindow(QMainWindow):
    """PySide6 GUI used for testing a modern replacement UI."""

    def __init__(self, preferences_path: str | Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 780)
        self._last_image_path: Path | None = None
        self.drawer_pinned = True
        self._last_drawer_width = DEFAULT_DRAWER_WIDTH
        self._preferences_path = Path(preferences_path) if preferences_path is not None else None
        self._preferences = load_preferences(self._preferences_path)

        self._apply_theme()
        self._build_ui()
        self._apply_preferences(self._preferences)
        self.statusBar().showMessage("Ready. Experimental PySide6 GUI; Tk GUI remains unchanged.")

    # ------------------------------------------------------------------
    # Theme and layout
    # ------------------------------------------------------------------
    def _apply_theme(self) -> None:
        qss_path = Path(__file__).with_name("theme.qss")
        if qss_path.exists():
            self.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 12)
        root.setSpacing(14)
        self.setCentralWidget(central)

        header = QHBoxLayout()
        title = QLabel(APP_TITLE)
        title.setObjectName("TitleLabel")
        subtitle = QLabel("PySide6 testing branch · existing Tkinter GUI is still available")
        subtitle.setObjectName("MutedLabel")
        subtitle.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.show_drawer_button = self._button("Show controls", self.show_control_drawer)
        self.show_drawer_button.setObjectName("DrawerShowButton")
        self.show_drawer_button.setVisible(False)
        header.addWidget(title, 1)
        header.addWidget(subtitle, 1)
        header.addWidget(self.show_drawer_button)
        root.addLayout(header)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setObjectName("MainSplitter")
        root.addWidget(self.main_splitter, 1)

        preview_card = self._build_preview_card()
        preview_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.main_splitter.addWidget(preview_card)

        self.drawer = self._build_control_drawer()
        self.drawer.setMinimumWidth(360)
        self.drawer.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.main_splitter.addWidget(self.drawer)
        self.main_splitter.setStretchFactor(0, 3)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([810, DEFAULT_DRAWER_WIDTH])

        self.setStatusBar(QStatusBar())

    def _card(self, title: str) -> QGroupBox:
        return QGroupBox(title)

    def _accent_button(self, text: str, callback: Callable[[], None]) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("AccentButton")
        button.clicked.connect(callback)
        return button

    def _button(self, text: str, callback: Callable[[], None]) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(callback)
        return button

    def _drawer_utility_button(self, text: str, callback: Callable[[], None]) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setObjectName("DrawerUtilityButton")
        button.clicked.connect(callback)
        return button

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------
    def _build_preview_card(self) -> QGroupBox:
        card = self._card("Screen preview")
        layout = QVBoxLayout(card)
        layout.setSpacing(10)

        self.preview_label = QLabel("Capture preview to show the scope screen here.")
        self.preview_label.setObjectName("PreviewLabel")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(640, 420)
        self.preview_label.setScaledContents(False)
        layout.addWidget(self.preview_label, 1)

        buttons = QHBoxLayout()
        buttons.addWidget(self._button("Capture preview", self.capture_preview))
        buttons.addWidget(self._button("Copy preview", self.copy_preview))
        buttons.addWidget(self._button("Save PNG image...", self.save_png_image))
        buttons.addWidget(self._accent_button("Save enabled channels to CSV...", self.save_csv))
        layout.addLayout(buttons)
        return card

    # ------------------------------------------------------------------
    # Resizable control drawer
    # ------------------------------------------------------------------
    def _build_control_drawer(self) -> QWidget:
        drawer = QWidget()
        drawer.setObjectName("ControlDrawer")
        layout = QHBoxLayout(drawer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        content = QWidget()
        content.setObjectName("DrawerContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 10, 12, 12)
        content_layout.setSpacing(10)

        header = QWidget()
        header.setObjectName("DrawerHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        self.drawer_title = QLabel(DRAWER_PAGE_TITLES[0])
        self.drawer_title.setObjectName("DrawerTitle")
        header_layout.addWidget(self.drawer_title, 1)
        content_layout.addWidget(header)

        self.drawer_stack = QStackedWidget()
        self.drawer_stack.setObjectName("DrawerStack")
        self.drawer_stack.addWidget(self._build_connection_tab())
        self.drawer_stack.addWidget(self._build_channels_tab())
        self.drawer_stack.addWidget(self._build_measurement_tab())
        self.drawer_stack.addWidget(self._build_trigger_tab())
        self.drawer_stack.addWidget(self._build_settings_tab())
        self.drawer_stack.addWidget(self._build_log_tab())
        content_layout.addWidget(self.drawer_stack, 1)
        layout.addWidget(content, 1)

        nav = QWidget()
        nav.setObjectName("DrawerNav")
        nav.setMinimumWidth(156)
        nav.setMaximumWidth(190)
        nav.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(6)

        nav_controls = QWidget()
        nav_controls.setObjectName("DrawerControls")
        nav_controls_layout = QHBoxLayout(nav_controls)
        nav_controls_layout.setContentsMargins(0, 0, 0, 0)
        nav_controls_layout.setSpacing(6)
        self.pin_drawer_button = self._drawer_utility_button("Pinned", self.toggle_drawer_pin)
        self.pin_drawer_button.setCheckable(True)
        self.pin_drawer_button.setChecked(True)
        self.hide_drawer_button = self._drawer_utility_button("Hide", self.hide_control_drawer)
        self.hide_drawer_button.setEnabled(False)
        nav_controls_layout.addWidget(self.pin_drawer_button, 1)
        nav_controls_layout.addWidget(self.hide_drawer_button, 1)
        nav_layout.addWidget(nav_controls)

        self.drawer_buttons = QButtonGroup(self)
        self.drawer_buttons.setExclusive(True)
        for index, title in enumerate(DRAWER_PAGE_TITLES):
            button = QToolButton()
            button.setText(title)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            button.setObjectName("DrawerNavButton")
            button.setMinimumHeight(42)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.clicked.connect(lambda checked=False, page=index: self._select_drawer_page(page))
            self.drawer_buttons.addButton(button, index)
            nav_layout.addWidget(button)
        nav_layout.addStretch(1)
        layout.addWidget(nav)

        first_button = self.drawer_buttons.button(0)
        if first_button is not None:
            first_button.setChecked(True)
        return drawer

    def _select_drawer_page(self, index: int) -> None:
        self.show_control_drawer()
        self.drawer_stack.setCurrentIndex(index)
        self.drawer_title.setText(DRAWER_PAGE_TITLES[index])
        button = self.drawer_buttons.button(index)
        if button is not None:
            button.setChecked(True)

    def toggle_drawer_pin(self) -> None:
        self.drawer_pinned = self.pin_drawer_button.isChecked()
        self.pin_drawer_button.setText("Pinned" if self.drawer_pinned else "Hideable")
        self.hide_drawer_button.setEnabled(not self.drawer_pinned)
        message = "Control drawer pinned open" if self.drawer_pinned else "Control drawer can now be hidden"
        self.statusBar().showMessage(message)

    def hide_control_drawer(self) -> None:
        if self.drawer_pinned:
            self.statusBar().showMessage("Unpin the control drawer before hiding it")
            return
        self._last_drawer_width = max(self.drawer.width(), 360)
        self.drawer.setVisible(False)
        self.show_drawer_button.setVisible(True)
        self.statusBar().showMessage("Control drawer hidden")

    def show_control_drawer(self) -> None:
        if self.drawer.isVisible():
            return
        self.drawer.setVisible(True)
        self.show_drawer_button.setVisible(False)
        preview_width = max(self.width() - self._last_drawer_width - 80, 520)
        self.main_splitter.setSizes([preview_width, self._last_drawer_width])
        self.statusBar().showMessage("Control drawer shown")

    # ------------------------------------------------------------------
    # Drawer pages
    # ------------------------------------------------------------------
    def _build_connection_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        card = self._card("Connection")
        form = QFormLayout(card)

        mode_box = QWidget()
        mode_layout = QHBoxLayout(mode_box)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        self.usb_mode = QRadioButton("USB / VISA")
        self.eth_mode = QRadioButton("Ethernet")
        self.usb_mode.setChecked(True)
        self.usb_mode.toggled.connect(lambda checked: checked and self._on_connection_mode_changed())
        self.eth_mode.toggled.connect(lambda checked: checked and self._on_connection_mode_changed())
        mode_layout.addWidget(self.usb_mode)
        mode_layout.addWidget(self.eth_mode)
        mode_layout.addStretch(1)
        form.addRow("Mode", mode_box)

        resource_box = QWidget()
        resource_layout = QHBoxLayout(resource_box)
        resource_layout.setContentsMargins(0, 0, 0, 0)
        resource_layout.setSpacing(8)
        self.resource = QComboBox()
        self.resource.setEditable(True)
        self.resource.addItem(visaResourceAddr)
        resource_layout.addWidget(self.resource, 1)
        resource_layout.addWidget(self._button("Refresh", self.refresh_visa_resources))
        form.addRow("VISA resource", resource_box)

        self.eth_host = QLineEdit()
        self.eth_port = QLineEdit("4000")
        self.eth_protocol = QComboBox()
        self.eth_protocol.addItems(["VXI-11 / INSTR", "Raw SOCKET"])
        self.generated_resource = QLineEdit()
        self.generated_resource.setReadOnly(True)
        self.timeout_ms = QLineEdit("20000")

        self.eth_host.textChanged.connect(lambda _text: self._refresh_generated_ethernet_resource())
        self.eth_port.textChanged.connect(lambda _text: self._refresh_generated_ethernet_resource())
        self.eth_protocol.currentTextChanged.connect(lambda _text: self._refresh_generated_ethernet_resource())

        form.addRow("Ethernet IP/host", self.eth_host)
        form.addRow("Protocol", self.eth_protocol)
        form.addRow("Socket port", self.eth_port)
        form.addRow("Generated resource", self.generated_resource)
        form.addRow("Timeout ms", self.timeout_ms)

        ethernet_button_row = QHBoxLayout()
        ethernet_button_row.addWidget(self._button("Use Ethernet resource", self.apply_ethernet_resource))
        ethernet_button_row.addWidget(self._accent_button("Test IDN", self.test_connection))
        form.addRow(ethernet_button_row)

        hint = QLabel("VXI-11: TCPIP0::<ip>::INSTR. Socket: TCPIP0::<ip>::4000::SOCKET.")
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        form.addRow(hint)

        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_channels_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        card = self._card("Channel labels")
        form = QFormLayout(card)
        self.channel_labels: dict[int, QLineEdit] = {}
        for channel in range(1, 5):
            edit = QLineEdit()
            self.channel_labels[channel] = edit
            form.addRow(f"CH{channel} label", edit)

        buttons = QHBoxLayout()
        buttons.addWidget(self._button("Read labels", self.read_labels))
        buttons.addWidget(self._accent_button("Apply labels", self.apply_labels))
        form.addRow(buttons)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_measurement_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        card = self._card("Measurement")
        form = QFormLayout(card)

        self.measurement_slot = QComboBox()
        self.measurement_slot.addItems([str(slot) for slot in MEASUREMENT_SLOTS])
        self.measurement_group = QComboBox()
        self.measurement_group.addItems(list(MEASUREMENT_TYPES_BY_GROUP))
        self.measurement_type = QComboBox()
        self.measurement_type.setEditable(True)
        self.measurement_group.currentTextChanged.connect(self._update_measurement_types)
        self._update_measurement_types(self.measurement_group.currentText())
        self.measurement_source1 = QComboBox()
        self.measurement_source1.addItems(MEASUREMENT_SOURCES)
        self.measurement_source2 = QComboBox()
        self.measurement_source2.addItems([""] + list(MEASUREMENT_SOURCES))
        self.measurement_value = QLineEdit()
        self.measurement_value.setReadOnly(True)

        form.addRow("Slot", self.measurement_slot)
        form.addRow("Group", self.measurement_group)
        form.addRow("Measurement type", self.measurement_type)
        form.addRow("Source 1", self.measurement_source1)
        form.addRow("Source 2", self.measurement_source2)
        form.addRow("Last read value", self.measurement_value)

        buttons = QHBoxLayout()
        buttons.addWidget(self._accent_button("Add / update", self.add_measurement))
        buttons.addWidget(self._button("Read value", self.read_measurement_value))
        buttons.addWidget(self._button("Clear slot", self.clear_measurement_slot))
        buttons.addWidget(self._button("Clear all", self.clear_all_measurements))
        form.addRow(buttons)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_trigger_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._build_image_rearm_card())
        layout.addWidget(self._build_trigger_actions_card())
        layout.addWidget(self._build_trigger_level_card())
        layout.addWidget(self._build_edge_trigger_card())
        layout.addStretch(1)
        return page

    def _build_image_rearm_card(self) -> QGroupBox:
        card = self._card("Image capture re-arm")
        form = QFormLayout(card)
        self.rearm_after_image = QCheckBox("Re-arm trigger after image capture")
        self.rearm_after_image.setChecked(True)
        self.trigger_channel_after_image = QComboBox()
        self.trigger_channel_after_image.addItems(["", "1", "2", "3", "4"])
        form.addRow(self.rearm_after_image)
        form.addRow("Trigger channel after image", self.trigger_channel_after_image)
        return card

    def _build_trigger_actions_card(self) -> QGroupBox:
        card = self._card("Acquisition / trigger actions")
        grid = QGridLayout(card)
        grid.addWidget(self._button("Run", self.run_acquisition), 0, 0)
        grid.addWidget(self._button("Stop", self.stop_acquisition), 0, 1)
        grid.addWidget(self._button("Single", self.single_acquisition), 0, 2)
        grid.addWidget(self._button("Continuous", self.continuous_acquisition), 0, 3)
        grid.addWidget(self._accent_button("Force trigger", self.force_trigger), 1, 0, 1, 4)
        return card

    def _build_trigger_level_card(self) -> QGroupBox:
        card = self._card("Trigger level / horizontal position")
        form = QFormLayout(card)
        self.trigger_channel = QComboBox()
        self.trigger_channel.addItems(["1", "2", "3", "4"])
        self.trigger_level = QLineEdit("1.0")
        self.trigger_set_source = QCheckBox("Set edge trigger source to selected channel")
        self.trigger_set_source.setChecked(True)
        self.trigger_readback = QLineEdit()
        self.trigger_readback.setReadOnly(True)
        self.horizontal_position = QLineEdit("0")
        form.addRow("Source", self.trigger_channel)
        form.addRow("Level V", self.trigger_level)
        form.addRow(self.trigger_set_source)
        form.addRow("Readback", self.trigger_readback)
        form.addRow("Horizontal position", self.horizontal_position)

        trigger_buttons = QHBoxLayout()
        trigger_buttons.addWidget(self._button("Read level", self.read_trigger_level))
        trigger_buttons.addWidget(self._accent_button("Set level", self.apply_trigger_level))
        form.addRow(trigger_buttons)

        horizontal_buttons = QHBoxLayout()
        horizontal_buttons.addWidget(self._button("Read position", self.read_horizontal_position))
        horizontal_buttons.addWidget(self._button("-10", lambda: self.nudge_horizontal_position(-10)))
        horizontal_buttons.addWidget(self._button("-1", lambda: self.nudge_horizontal_position(-1)))
        horizontal_buttons.addWidget(self._button("Center 0", self.set_horizontal_position_to_zero))
        horizontal_buttons.addWidget(self._button("+1", lambda: self.nudge_horizontal_position(1)))
        horizontal_buttons.addWidget(self._button("+10", lambda: self.nudge_horizontal_position(10)))
        form.addRow(horizontal_buttons)
        form.addRow(self._button("Set position", self.set_horizontal_position))
        return card

    def _build_edge_trigger_card(self) -> QGroupBox:
        card = self._card("Edge trigger setup")
        form = QFormLayout(card)
        self.edge_mode = QComboBox()
        self.edge_mode.addItems(TRIGGER_MODES)
        self.edge_source = QComboBox()
        self.edge_source.addItems(TRIGGER_SOURCES)
        self.edge_slope = QComboBox()
        self.edge_slope.addItems(TRIGGER_SLOPES)
        self.edge_coupling = QComboBox()
        self.edge_coupling.addItems(TRIGGER_COUPLINGS)
        self.edge_level = QLineEdit("1.0")
        form.addRow("Mode", self.edge_mode)
        form.addRow("Source", self.edge_source)
        form.addRow("Slope", self.edge_slope)
        form.addRow("Coupling", self.edge_coupling)
        form.addRow("Level", self.edge_level)
        form.addRow(self._accent_button("Apply edge trigger", self.apply_edge_trigger))
        return card

    def _build_settings_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        card = self._card("Output and scope settings")
        form = QFormLayout(card)

        folder_box = QWidget()
        folder_layout = QHBoxLayout(folder_box)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(8)
        self.output_folder = QLineEdit(str(resolve_output_folder("scope_gui_output")))
        folder_layout.addWidget(self.output_folder, 1)
        folder_layout.addWidget(self._button("Pick folder", self.pick_output_folder))
        form.addRow("Destination folder", folder_box)

        hint = QLabel("Filename format: <prefix><base><_timestamp optional>.<extension>")
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        form.addRow(hint)

        self.png_prefix, self.png_base, self.png_timestamp = self._add_naming_row(
            form,
            "PNG images",
            "scope_",
            "screen",
            True,
        )
        self.csv_prefix, self.csv_base, self.csv_timestamp = self._add_naming_row(
            form,
            "CSV waveforms",
            "scope_",
            "waveform",
            True,
        )
        self.settings_prefix, self.settings_base, self.settings_timestamp = self._add_naming_row(
            form,
            "Settings JSON",
            "dpo4054_",
            "setup",
            True,
        )

        self.restore_wait_opc = QCheckBox("Wait for *OPC? after restore (can timeout on DPO4000)")
        form.addRow(self.restore_wait_opc)
        form.addRow(self._button("Save settings JSON", self.save_settings))
        form.addRow(self._accent_button("Restore settings JSON...", self.restore_settings))
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _add_naming_row(
        self,
        form: QFormLayout,
        title: str,
        default_prefix: str,
        default_base: str,
        timestamp: bool,
    ) -> tuple[QLineEdit, QLineEdit, QCheckBox]:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        prefix = QLineEdit(default_prefix)
        prefix.setMaximumWidth(105)
        base = QLineEdit(default_base)
        timestamp_check = QCheckBox("Timestamp")
        timestamp_check.setChecked(timestamp)
        layout.addWidget(QLabel("Prefix"))
        layout.addWidget(prefix)
        layout.addWidget(QLabel("Base"))
        layout.addWidget(base, 1)
        layout.addWidget(timestamp_check)
        form.addRow(title, row)
        return prefix, base, timestamp_check

    def _build_log_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
        return page

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------
    def _apply_preferences(self, preferences: GuiPreferences) -> None:
        self.eth_host.setText(preferences.ethernet_host)
        self.eth_port.setText(preferences.ethernet_port)
        self._set_combo_text(self.eth_protocol, preferences.ethernet_protocol)
        self.timeout_ms.setText(preferences.timeout_ms)
        self.output_folder.setText(preferences.output_folder)
        self.png_prefix.setText(preferences.png_prefix)
        self.png_base.setText(preferences.png_base)
        self.png_timestamp.setChecked(preferences.png_add_timestamp)
        self.csv_prefix.setText(preferences.csv_prefix)
        self.csv_base.setText(preferences.csv_base)
        self.csv_timestamp.setChecked(preferences.csv_add_timestamp)
        self.settings_prefix.setText(preferences.settings_prefix)
        self.settings_base.setText(preferences.settings_base)
        self.settings_timestamp.setChecked(preferences.settings_add_timestamp)
        self.restore_wait_opc.setChecked(preferences.restore_wait_opc)
        self.rearm_after_image.setChecked(preferences.rearm_after_image)
        self._set_combo_text(self.trigger_channel_after_image, preferences.trigger_channel_after_image)
        self._set_combo_text(self.trigger_channel, preferences.trigger_setup_channel)
        self.trigger_level.setText(preferences.trigger_level)
        self.trigger_set_source.setChecked(preferences.trigger_set_source)
        self._update_visa_resource_list((preferences.visa_resource,))
        self._set_combo_text(self.resource, preferences.visa_resource)
        if preferences.connection_mode == "ethernet":
            self.eth_mode.setChecked(True)
        else:
            self.usb_mode.setChecked(True)
        self._refresh_generated_ethernet_resource()

    def _collect_preferences(self) -> GuiPreferences:
        return GuiPreferences(
            connection_mode="ethernet" if self.eth_mode.isChecked() else "visa",
            visa_resource=self.resource.currentText(),
            ethernet_host=self.eth_host.text(),
            ethernet_port=self.eth_port.text(),
            ethernet_protocol=self.eth_protocol.currentText(),
            timeout_ms=self.timeout_ms.text(),
            output_folder=self.output_folder.text(),
            png_prefix=self.png_prefix.text(),
            png_base=self.png_base.text(),
            png_add_timestamp=self.png_timestamp.isChecked(),
            csv_prefix=self.csv_prefix.text(),
            csv_base=self.csv_base.text(),
            csv_add_timestamp=self.csv_timestamp.isChecked(),
            settings_prefix=self.settings_prefix.text(),
            settings_base=self.settings_base.text(),
            settings_add_timestamp=self.settings_timestamp.isChecked(),
            restore_wait_opc=self.restore_wait_opc.isChecked(),
            rearm_after_image=self.rearm_after_image.isChecked(),
            trigger_channel_after_image=self.trigger_channel_after_image.currentText(),
            trigger_setup_channel=self.trigger_channel.currentText(),
            trigger_level=self.trigger_level.text(),
            trigger_set_source=self.trigger_set_source.isChecked(),
        )

    def _save_preferences_safely(self) -> Path | None:
        try:
            return save_preferences(self._collect_preferences(), self._preferences_path)
        except Exception as exc:
            self._append_log(f"Could not save GUI preferences: {exc}")
            return None

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API name
        self._save_preferences_safely()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Connection / validation / path helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _set_combo_text(combo: QComboBox, value: str) -> None:
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif combo.isEditable():
            combo.setEditText(value)
        elif value:
            combo.addItem(value)
            combo.setCurrentText(value)

    def _on_connection_mode_changed(self) -> None:
        if self.eth_mode.isChecked():
            self._refresh_generated_ethernet_resource()

    def _ethernet_resource_name(self) -> str:
        host = self.eth_host.text().strip()
        if not host:
            raise ValueError("Ethernet IP/host cannot be empty.")
        if self.eth_protocol.currentText() == "Raw SOCKET":
            port_text = self.eth_port.text().strip() or "4000"
            port = int(port_text)
            if port < 1 or port > 65535:
                raise ValueError("Ethernet socket port must be between 1 and 65535.")
            return build_tcpip_socket_resource(host, port)
        return build_tcpip_instr_resource(host)

    def _selected_resource(self) -> str:
        if self.eth_mode.isChecked():
            resource = self._ethernet_resource_name()
            self.generated_resource.setText(resource)
            return resource
        resource = self.resource.currentText().strip()
        if not resource:
            raise ValueError("VISA resource cannot be empty.")
        return resource

    def _timeout(self) -> int:
        try:
            timeout = int(self.timeout_ms.text().strip())
        except ValueError as exc:
            raise ValueError("Timeout must be an integer in milliseconds.") from exc
        if timeout < 1000:
            raise ValueError("Timeout should be at least 1000 ms.")
        return timeout

    def _configured_output_folder(self, *, create: bool = True) -> Path:
        folder = resolve_output_folder(self.output_folder.text())
        if create:
            folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _build_output_path(self, kind: str) -> Path:
        if kind == "png":
            naming = FileNaming(
                prefix=self.png_prefix.text(),
                base=self.png_base.text(),
                extension=".png",
                fallback="scope_screen",
                add_timestamp=self.png_timestamp.isChecked(),
            )
        elif kind == "csv":
            naming = FileNaming(
                prefix=self.csv_prefix.text(),
                base=self.csv_base.text(),
                extension=".csv",
                fallback="scope_waveform",
                add_timestamp=self.csv_timestamp.isChecked(),
            )
        elif kind == "settings":
            naming = FileNaming(
                prefix=self.settings_prefix.text(),
                base=self.settings_base.text(),
                extension=".json",
                fallback="dpo4054_setup",
                add_timestamp=self.settings_timestamp.isChecked(),
            )
        else:
            raise ValueError(f"Unknown output kind: {kind}")
        return build_output_path(self.output_folder.text(), naming)

    def _confirm_or_cancel_overwrite(self, path: Path) -> bool:
        if not path.exists():
            return True
        answer = QMessageBox.question(
            self,
            APP_TITLE,
            f"File already exists:\n{path}\n\nOverwrite it?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return answer == QMessageBox.Yes

    @staticmethod
    def _safe_label_text(text: str) -> str:
        return text.replace('"', "'")[:30]

    def _rearm_after_image_enabled(self) -> bool:
        return self.rearm_after_image.isChecked()

    def _trigger_channel_or_none(self) -> int | None:
        value = self.trigger_channel_after_image.currentText().strip()
        if not value:
            return None
        channel = int(value)
        validate_channel(channel)
        return channel

    def _selected_trigger_channel(self) -> int:
        channel = int(self.trigger_channel.currentText())
        validate_channel(channel)
        return channel

    def _parsed_trigger_level(self, value: str | None = None) -> float | str:
        raw_value = (value if value is not None else self.trigger_level.text()).strip()
        if not raw_value:
            raise ValueError("Trigger level cannot be empty.")
        preset = raw_value.upper()
        if preset in {"TTL", "ECL"}:
            return preset
        try:
            return float(raw_value)
        except ValueError as exc:
            raise ValueError("Trigger level must be a number in volts, or TTL/ECL.") from exc

    def _new_scope_session(self, callback: Callable[[DPO4054], object]) -> object:
        scope = DPO4054(self._selected_resource(), auto_connect=False)
        try:
            scope.connect()
            if getattr(scope, "scope", None) is not None:
                scope.scope.timeout = self._timeout()
                try:
                    scope.scope.write_termination = "\n"
                    scope.scope.read_termination = "\n"
                except Exception:
                    pass
            return callback(scope)
        finally:
            with contextlib.suppress(Exception):
                scope.disconnect()

    def _refresh_generated_ethernet_resource(self) -> None:
        if not self.eth_host.text().strip():
            self.generated_resource.setText("")
            return
        try:
            self.generated_resource.setText(self._ethernet_resource_name())
        except Exception:
            self.generated_resource.setText("")

    def _update_visa_resource_list(self, resources: tuple[str, ...]) -> None:
        current = self.resource.currentText().strip()
        values: list[str] = []
        for resource in resources:
            text = str(resource)
            if text and text not in values:
                values.append(text)
        if current and current not in values:
            values.insert(0, current)
        if visaResourceAddr and visaResourceAddr not in values:
            values.append(visaResourceAddr)
        self.resource.clear()
        self.resource.addItems(values)
        if current:
            self._set_combo_text(self.resource, current)

    def apply_ethernet_resource(self) -> None:
        try:
            resource = self._ethernet_resource_name()
        except Exception as exc:
            self._message("Ethernet resource", str(exc), error=True)
            return
        self.generated_resource.setText(resource)
        self._set_combo_text(self.resource, resource)
        self.eth_mode.setChecked(True)
        self._append_log(f"Ethernet resource selected: {resource}")
        self.statusBar().showMessage(f"Ethernet resource selected: {resource}")

    # ------------------------------------------------------------------
    # GUI actions
    # ------------------------------------------------------------------
    def refresh_visa_resources(self) -> None:
        self.statusBar().showMessage("Refreshing VISA resources")
        try:
            resources = list_visa_resources()
        except Exception as exc:
            self._append_log(f"ERROR: {exc}")
            self._message("Refresh VISA resources", str(exc), error=True)
            return
        self._update_visa_resource_list(resources)
        if resources:
            message = "VISA resources found:\n" + "\n".join(resources)
        else:
            message = "No VISA resources found."
        self._append_log(message)
        self._message("Refresh VISA resources", message)
        self.statusBar().showMessage("VISA resource list refreshed")

    def pick_output_folder(self) -> None:
        initial_dir = str(self._configured_output_folder(create=False))
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select output folder for PNG, CSV, and scope settings",
            initial_dir,
        )
        if selected:
            self.output_folder.setText(selected)
            folder = self._configured_output_folder(create=True)
            self._append_log(f"Output folder set to: {folder}")
            self.statusBar().showMessage(f"Output folder set to: {folder}")

    def test_connection(self) -> None:
        result = self._run_action("Testing scope connection", lambda scope: scope.scope.query("*IDN?").strip())
        if result is not None:
            self._message("Scope IDN", str(result))

    def read_labels(self) -> None:
        result = self._run_action(
            "Reading CH1..CH4 labels",
            lambda scope: {channel: scope.get_channel_label(channel) for channel in range(1, 5)},
        )
        if isinstance(result, dict):
            for channel, label in result.items():
                self.channel_labels[int(channel)].setText(str(label))

    def apply_labels(self) -> None:
        labels = {channel: self._safe_label_text(edit.text()) for channel, edit in self.channel_labels.items()}

        def action(scope: DPO4054) -> dict[int, str]:
            for channel, label in labels.items():
                scope.set_channel_label(channel, label)
            return {channel: scope.get_channel_label(channel) for channel in range(1, 5)}

        result = self._run_action("Applying CH1..CH4 labels", action)
        if isinstance(result, dict):
            for channel, label in result.items():
                self.channel_labels[int(channel)].setText(str(label))

    def capture_preview(self) -> None:
        path = self._build_output_path("png")
        if not self._confirm_or_cancel_overwrite(path):
            return
        self._capture_image_to(path, "Capturing scope image preview")

    def save_png_image(self) -> None:
        path = self._build_output_path("png")
        if not self._confirm_or_cancel_overwrite(path):
            return
        self._capture_image_to(path, "Saving scope PNG image")

    def _capture_image_to(self, path: Path, description: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        rearm = self._rearm_after_image_enabled()
        trigger_channel = self._trigger_channel_or_none()

        def action(scope: DPO4054) -> str:
            saved_path = save_screen_png(getattr(scope, "scope", None), path)
            if rearm:
                scope.rearm_trigger_after_image(trigger_channel=trigger_channel)
            return str(saved_path)

        result = self._run_action(description, action)
        if isinstance(result, str):
            self._last_image_path = Path(result)
            self._load_preview(self._last_image_path)

    def _load_preview(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.preview_label.setText(f"Image saved, but preview could not be loaded:\n{path}")
            return
        self.preview_label.setPixmap(
            pixmap.scaled(
                self.preview_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def copy_preview(self) -> None:
        if self._last_image_path is None or not self._last_image_path.exists():
            self._message("Copy preview", "No captured preview image is available yet.")
            return
        pixmap = QPixmap(str(self._last_image_path))
        if pixmap.isNull():
            self._message("Copy preview", "Captured image could not be loaded.")
            return
        QApplication.clipboard().setPixmap(pixmap)
        self._append_log(f"Copied preview to clipboard: {self._last_image_path}")
        self.statusBar().showMessage("Preview copied to clipboard")

    def save_csv(self) -> None:
        path = self._build_output_path("csv")
        if not self._confirm_or_cancel_overwrite(path):
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        result = self._run_action(
            "Saving enabled channel waveforms to CSV",
            lambda scope: str(save_enabled_channels_to_single_csv(getattr(scope, "scope", None), path)),
        )
        if result is not None:
            self._message("CSV saved", str(result))

    def save_settings(self) -> None:
        path = self._build_output_path("settings")
        if not self._confirm_or_cancel_overwrite(path):
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        result = self._run_action(
            "Saving scope settings JSON",
            lambda scope: str(scope.save_scope_settings(str(path), ask_before_overwrite=False)),
        )
        if result is not None:
            self._message("Settings saved", str(result))

    def restore_settings(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Restore scope settings JSON",
            str(self._configured_output_folder(create=True)),
            "JSON files (*.json);;All files (*.*)",
        )
        if not selected:
            return
        path = Path(selected)
        wait_opc = self.restore_wait_opc.isChecked()
        result = self._run_action(
            "Restoring scope settings JSON",
            lambda scope: apply_scope_settings_file(
                getattr(scope, "scope", None),
                path,
                wait_complete=wait_opc,
                check_error=True,
                opc_timeout_ms=DEFAULT_RESTORE_TIMEOUT_MS,
            ),
        )
        if isinstance(result, dict):
            self._message("Settings restored", f"Instrument: {result.get('instrument', 'Unknown')}")

    def _selected_measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            slot=int(self.measurement_slot.currentText()),
            measurement_type=self.measurement_type.currentText(),
            source1=self.measurement_source1.currentText(),
            source2=self.measurement_source2.currentText() or None,
        )

    def add_measurement(self) -> None:
        config = self._selected_measurement_config()
        self._run_action(
            f"Adding {config.measurement_type.upper()} measurement to MEAS{config.slot}",
            lambda scope: scope.add_measurement(config),
        )

    def read_measurement_value(self) -> None:
        slot = int(self.measurement_slot.currentText())
        result = self._run_action("Reading measurement", lambda scope: scope.read_measurement_value(slot))
        if result is not None:
            self.measurement_value.setText(str(result))

    def clear_measurement_slot(self) -> None:
        slot = int(self.measurement_slot.currentText())
        self._run_action("Clearing measurement slot", lambda scope: scope.disable_measurement(slot))

    def clear_all_measurements(self) -> None:
        self._run_action("Clearing all measurement slots", lambda scope: scope.disable_all_measurements())

    def read_trigger_level(self) -> None:
        channel = self._selected_trigger_channel()
        result = self._run_action(
            f"Reading trigger level for CH{channel}",
            lambda scope: scope.get_trigger_level(channel=channel),
        )
        if result is not None:
            self.trigger_readback.setText(str(result))

    def apply_trigger_level(self) -> None:
        channel = self._selected_trigger_channel()
        level = self._parsed_trigger_level()
        set_source = self.trigger_set_source.isChecked()

        def action(scope: DPO4054) -> object:
            if set_source:
                scope.set_edge_trigger_source(channel)
            readback = scope.set_trigger_level(level, channel=channel, verify=True)
            with contextlib.suppress(Exception):
                scope.scope.write("ACQUIRE:STATE RUN")
            return readback

        result = self._run_action(f"Setting trigger CH{channel} level to {level}", action)
        if result is not None:
            self.trigger_readback.setText(str(result))

    def read_horizontal_position(self) -> None:
        result = self._run_action("Reading horizontal position", lambda scope: scope.get_horizontal_position())
        if result is not None:
            self.horizontal_position.setText(f"{float(result):g}")

    def set_horizontal_position(self) -> None:
        value = self.horizontal_position.text().strip()
        self._run_action("Setting horizontal position", lambda scope: scope.set_horizontal_position(value))

    def nudge_horizontal_position(self, delta: int | float) -> None:
        result = self._run_action(
            f"Nudging horizontal position by {delta:g}",
            lambda scope: scope.nudge_horizontal_position(delta),
        )
        if result is not None:
            self.horizontal_position.setText(f"{float(result):g}")

    def set_horizontal_position_to_zero(self) -> None:
        self.horizontal_position.setText("0")
        self.set_horizontal_position()

    def run_acquisition(self) -> None:
        self._run_action("Starting acquisition", lambda scope: scope.run_acquisition())

    def stop_acquisition(self) -> None:
        self._run_action("Stopping acquisition", lambda scope: scope.stop_acquisition())

    def single_acquisition(self) -> None:
        self._run_action("Starting single acquisition", lambda scope: scope.single_acquisition())

    def continuous_acquisition(self) -> None:
        self._run_action("Returning acquisition to continuous mode", lambda scope: scope.continuous_acquisition())

    def force_trigger(self) -> None:
        self._run_action("Forcing trigger event", lambda scope: scope.force_trigger_event())

    def apply_edge_trigger(self) -> None:
        level = self._parsed_trigger_level(self.edge_level.text())
        self._run_action(
            "Applying edge trigger",
            lambda scope: scope.configure_edge_trigger(
                source=self.edge_source.currentText(),
                slope=self.edge_slope.currentText(),
                coupling=self.edge_coupling.currentText(),
                mode=self.edge_mode.currentText(),
                level=level,
            ),
        )

    def _run_action(self, description: str, callback: Callable[[DPO4054], object]) -> object | None:
        self.statusBar().showMessage(description)
        self._append_log(description)
        try:
            result = self._new_scope_session(callback)
        except Exception as exc:
            self.statusBar().showMessage(f"Failed: {description}")
            self._append_log(f"ERROR: {exc}")
            self._message(description, str(exc), error=True)
            return None
        self.statusBar().showMessage(f"Done: {description}")
        if result is not None:
            self._append_log(str(result))
        return result

    def _update_measurement_types(self, group: str) -> None:
        self.measurement_type.clear()
        self.measurement_type.addItems(MEASUREMENT_TYPES_BY_GROUP.get(group, ()))

    def _message(self, title: str, text: str, *, error: bool = False) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Critical if error else QMessageBox.Information)
        box.exec()

    def _append_log(self, text: str) -> None:
        with contextlib.suppress(Exception):
            self.log.append(text)


__all__ = ["APP_TITLE", "DEFAULT_DRAWER_WIDTH", "DRAWER_PAGE_TITLES", "QtScopeWindow"]
