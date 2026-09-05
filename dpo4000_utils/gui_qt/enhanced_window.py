"""Enhanced PySide6 window with compact controls, channel, and math configuration."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QKeySequence, QShortcut
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
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..control import ChannelConfig, MathConfig, bool_from_scope_response
from .main_window import DRAWER_PAGE_TITLES, QtScopeWindow as BaseQtScopeWindow

CHANNEL_CONFIG_FIELDS = (
    "display",
    "scale",
    "position",
    "offset",
    "coupling",
    "bandwidth",
    "invert",
    "probe_gain",
)
MATH_CONFIG_FIELDS = ("display", "define", "scale", "position")
DRAWER_NAV_LABELS = {
    "Connection": "Conn",
    "Channels": "Ch",
    "Measurement": "Meas",
    "Trigger": "Trig",
    "Settings": "Set",
    "Log": "Log",
}
DRAWER_PAGE_ICON_NAMES = {
    "Connection": "SP_DriveNetIcon",
    "Channels": "SP_ComputerIcon",
    "Measurement": "SP_FileDialogDetailedView",
    "Trigger": "SP_MediaPlay",
    "Settings": "SP_FileDialogInfoView",
    "Log": "SP_FileIcon",
}
DRAWER_NAV_ICON_SIZE = QSize(24, 24)


class QtScopeWindow(BaseQtScopeWindow):
    """Qt window variant with compact access to common controls."""

    def __init__(self, *args, **kwargs) -> None:
        self._advanced_widgets: list[QWidget] = []
        self.compact_mode = True
        super().__init__(*args, **kwargs)
        self._apply_compact_mode()

    # ------------------------------------------------------------------
    # Space-saving shell controls
    # ------------------------------------------------------------------
    def _build_preview_card(self) -> QGroupBox:
        """Build preview card without the redundant bottom action button row."""
        card = self._card("Screen preview")
        layout = QVBoxLayout(card)
        layout.setSpacing(10)
        layout.addWidget(self._build_quick_control_bar())

        self.preview_label = QLabel("Capture preview to show the scope screen here.")
        self.preview_label.setObjectName("PreviewLabel")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(640, 420)
        self.preview_label.setScaledContents(False)
        layout.addWidget(self.preview_label, 1)

        card.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        card.setToolTip("Click the screen preview, then press Ctrl+C to copy the current image.")
        self.preview_label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.preview_label.setToolTip("Click here, then press Ctrl+C to copy the current image.")
        self.preview_copy_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Copy), card)
        self.preview_copy_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.preview_copy_shortcut.activated.connect(self.copy_preview)
        return card

    def _quick_button(self, text: str, callback, *, accent: bool = False) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setObjectName("QuickAccentButton" if accent else "QuickControlButton")
        button.clicked.connect(callback)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        return button

    def _build_quick_control_bar(self) -> QWidget:
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
            ("Run", self.run_acquisition, False),
            ("Stop", self.stop_acquisition, False),
            ("Single", self.single_acquisition, False),
            ("Force", self.force_trigger, True),
        )
        for text, callback, accent in quick_actions:
            layout.addWidget(self._quick_button(text, callback, accent=accent))
        layout.addStretch(1)
        return toolbar

    def _drawer_icon_for_page(self, title: str):
        icon_name = DRAWER_PAGE_ICON_NAMES.get(title, "SP_FileIcon")
        standard_icon = getattr(QStyle.StandardPixmap, icon_name, QStyle.StandardPixmap.SP_FileIcon)
        return self.style().standardIcon(standard_icon)

    def _build_control_drawer(self) -> QWidget:
        """Build a resizable drawer with compact icon navigation on the far right."""
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
        self.compact_mode_button = QToolButton()
        self.compact_mode_button.setObjectName("CompactModeButton")
        self.compact_mode_button.setCheckable(True)
        self.compact_mode_button.setChecked(True)
        self.compact_mode_button.setText("Compact")
        self.compact_mode_button.setToolTip("Hide advanced drawer sections")
        self.compact_mode_button.clicked.connect(self.toggle_compact_mode)
        header_layout.addWidget(self.drawer_title, 1)
        header_layout.addWidget(self.compact_mode_button)
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
        nav.setMinimumWidth(88)
        nav.setMaximumWidth(108)
        nav.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(6, 8, 6, 8)
        nav_layout.setSpacing(6)

        nav_controls = QWidget()
        nav_controls.setObjectName("DrawerControls")
        nav_controls_layout = QHBoxLayout(nav_controls)
        nav_controls_layout.setContentsMargins(0, 0, 0, 0)
        nav_controls_layout.setSpacing(4)
        self.pin_drawer_button = self._drawer_utility_button("Pin", self.toggle_drawer_pin)
        self.pin_drawer_button.setCheckable(True)
        self.pin_drawer_button.setChecked(True)
        self.pin_drawer_button.setToolTip("Keep control drawer pinned open")
        self.hide_drawer_button = self._drawer_utility_button("Hide", self.hide_control_drawer)
        self.hide_drawer_button.setEnabled(False)
        self.hide_drawer_button.setToolTip("Hide control drawer after unpinning")
        nav_controls_layout.addWidget(self.pin_drawer_button, 1)
        nav_controls_layout.addWidget(self.hide_drawer_button, 1)
        nav_layout.addWidget(nav_controls)

        self.drawer_buttons = QButtonGroup(self)
        self.drawer_buttons.setExclusive(True)
        for index, title in enumerate(DRAWER_PAGE_TITLES):
            button = QToolButton()
            button.setText(DRAWER_NAV_LABELS.get(title, title))
            button.setToolTip(title)
            button.setIcon(self._drawer_icon_for_page(title))
            button.setIconSize(DRAWER_NAV_ICON_SIZE)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setObjectName("DrawerNavButton")
            button.setMinimumHeight(64)
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

    def toggle_drawer_pin(self) -> None:
        self.drawer_pinned = self.pin_drawer_button.isChecked()
        self.pin_drawer_button.setText("Pin" if self.drawer_pinned else "Free")
        self.pin_drawer_button.setToolTip(
            "Keep control drawer pinned open" if self.drawer_pinned else "Drawer can now be hidden"
        )
        self.hide_drawer_button.setEnabled(not self.drawer_pinned)
        message = "Control drawer pinned open" if self.drawer_pinned else "Control drawer can now be hidden"
        self.statusBar().showMessage(message)

    def toggle_compact_mode(self) -> None:
        self.compact_mode = self.compact_mode_button.isChecked()
        self._apply_compact_mode()
        mode = "Compact" if self.compact_mode else "Advanced"
        self.statusBar().showMessage(f"{mode} drawer mode")

    def _apply_compact_mode(self) -> None:
        for widget in getattr(self, "_advanced_widgets", []):
            widget.setVisible(not self.compact_mode)
        button = getattr(self, "compact_mode_button", None)
        if button is not None:
            button.setText("Compact" if self.compact_mode else "Advanced")
            button.setToolTip(
                "Hide advanced drawer sections" if self.compact_mode else "Show advanced drawer sections"
            )

    def _register_advanced_widget(self, widget: QWidget) -> QWidget:
        self._advanced_widgets.append(widget)
        widget.setVisible(not self.compact_mode)
        return widget

    @staticmethod
    def _prepare_drawer_card(card: QGroupBox) -> QGroupBox:
        """Keep cards at natural height inside drawer scroll pages."""
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return card

    @staticmethod
    def _keep_drawer_cards_natural_height(container: QWidget) -> None:
        """Prevent nested cards from being vertically compressed."""
        for card in container.findChildren(QGroupBox):
            QtScopeWindow._prepare_drawer_card(card)

    def _collapsible_section(self, title: str, content: QWidget, *, expanded: bool = False) -> QWidget:
        section = QWidget()
        section.setObjectName("CollapsibleSection")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QToolButton()
        header.setObjectName("CollapsibleHeader")
        header.setCheckable(True)
        header.setChecked(expanded)
        header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        header.setText(("▾ " if expanded else "▸ ") + title)
        header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        if isinstance(content, QGroupBox):
            content.setTitle("")
            content.setObjectName("CollapsibleContent")
            self._prepare_drawer_card(content)
        content.setVisible(expanded)

        def update_expanded(checked: bool) -> None:
            content.setVisible(checked)
            header.setText(("▾ " if checked else "▸ ") + title)

        header.toggled.connect(update_expanded)
        layout.addWidget(header)
        layout.addWidget(content)
        return self._register_advanced_widget(section)

    def _wrap_scrollable_drawer_page(
        self,
        body: QWidget,
        *,
        scroll_name: str,
        body_name: str,
    ) -> QScrollArea:
        body.setObjectName(body_name)
        if body.layout() is not None:
            body.layout().setContentsMargins(0, 0, 8, 0)
            body.layout().setSpacing(12)
        self._keep_drawer_cards_natural_height(body)

        scroll = QScrollArea()
        scroll.setObjectName(scroll_name)
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        return scroll

    # ------------------------------------------------------------------
    # Compact Trigger page
    # ------------------------------------------------------------------
    def _build_trigger_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_trigger_quick_card())
        layout.addWidget(self._collapsible_section("Horizontal position", self._build_horizontal_position_card()))
        layout.addWidget(self._collapsible_section("Edge trigger setup", self._build_edge_trigger_card()))
        layout.addWidget(self._collapsible_section("Image capture re-arm", self._build_image_rearm_card()))
        layout.addStretch(1)
        return self._wrap_scrollable_drawer_page(
            body,
            scroll_name="TriggerScrollArea",
            body_name="TriggerScrollBody",
        )

    def _build_trigger_quick_card(self) -> QGroupBox:
        card = self._card("Trigger quick")
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

        level_buttons = QHBoxLayout()
        level_buttons.addWidget(self._button("Read level", self.read_trigger_level))
        level_buttons.addWidget(self._accent_button("Set level", self.apply_trigger_level))
        form.addRow(level_buttons)

        action_grid = QGridLayout()
        action_grid.addWidget(self._button("Run", self.run_acquisition), 0, 0)
        action_grid.addWidget(self._button("Stop", self.stop_acquisition), 0, 1)
        action_grid.addWidget(self._button("Single", self.single_acquisition), 0, 2)
        action_grid.addWidget(self._button("Continuous", self.continuous_acquisition), 1, 0)
        action_grid.addWidget(self._accent_button("Force", self.force_trigger), 1, 1, 1, 2)
        form.addRow(action_grid)
        return self._prepare_drawer_card(card)

    def _build_horizontal_position_card(self) -> QGroupBox:
        card = self._card("Horizontal position")
        form = QFormLayout(card)
        self._prepare_form(form)
        self.horizontal_position = QLineEdit("0")
        form.addRow("Position", self.horizontal_position)

        buttons = QHBoxLayout()
        buttons.addWidget(self._button("Read", self.read_horizontal_position))
        buttons.addWidget(self._button("-10", lambda: self.nudge_horizontal_position(-10)))
        buttons.addWidget(self._button("-1", lambda: self.nudge_horizontal_position(-1)))
        buttons.addWidget(self._button("0", self.set_horizontal_position_to_zero))
        buttons.addWidget(self._button("+1", lambda: self.nudge_horizontal_position(1)))
        buttons.addWidget(self._button("+10", lambda: self.nudge_horizontal_position(10)))
        form.addRow(buttons)
        form.addRow(self._accent_button("Set position", self.set_horizontal_position))
        return self._prepare_drawer_card(card)

    # ------------------------------------------------------------------
    # Compact Channels page
    # ------------------------------------------------------------------
    def _build_channels_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_channel_labels_card())
        layout.addWidget(self._collapsible_section("Full channel configuration", self._build_channel_configuration_card()))
        layout.addWidget(self._collapsible_section("Math channel configuration", self._build_math_configuration_card()))
        layout.addStretch(1)
        return self._wrap_scrollable_drawer_page(
            body,
            scroll_name="ChannelsScrollArea",
            body_name="ChannelsScrollBody",
        )

    @staticmethod
    def _prepare_form(form: QFormLayout) -> None:
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(12)

    @staticmethod
    def _prepare_channels_card(card):
        return QtScopeWindow._prepare_drawer_card(card)

    def _build_channel_labels_card(self):
        card = self._card("Channel labels")
        form = QFormLayout(card)
        self._prepare_form(form)
        self.channel_labels: dict[int, QLineEdit] = {}
        for channel in range(1, 5):
            edit = QLineEdit()
            self.channel_labels[channel] = edit
            form.addRow(f"CH{channel} label", edit)

        buttons = QHBoxLayout()
        buttons.addWidget(self._button("Read labels", self.read_labels))
        buttons.addWidget(self._accent_button("Apply labels", self.apply_labels))
        form.addRow(buttons)
        return self._prepare_channels_card(card)

    def _build_channel_configuration_card(self):
        card = self._card("Full channel configuration")
        form = QFormLayout(card)
        self._prepare_form(form)

        self.channel_config_channel = QComboBox()
        self.channel_config_channel.addItems(["1", "2", "3", "4"])
        self.channel_config_display = QCheckBox("Show selected channel")
        self.channel_config_display.setChecked(True)
        self.channel_config_scale = QLineEdit("1.0")
        self.channel_config_position = QLineEdit("0")
        self.channel_config_offset = QLineEdit("0")
        self.channel_config_coupling = QComboBox()
        self.channel_config_coupling.setEditable(True)
        self.channel_config_coupling.addItems(["DC", "AC", "GND"])
        self.channel_config_bandwidth = QComboBox()
        self.channel_config_bandwidth.setEditable(True)
        self.channel_config_bandwidth.addItems(["", "FULL", "20E6", "250E6"])
        self.channel_config_invert = QCheckBox("Invert waveform")
        self.channel_config_probe_gain = QLineEdit("")

        form.addRow("Channel", self.channel_config_channel)
        form.addRow("Display", self.channel_config_display)
        form.addRow("Vertical scale V/div", self.channel_config_scale)
        form.addRow("Vertical position div", self.channel_config_position)
        form.addRow("Vertical offset V", self.channel_config_offset)
        form.addRow("Coupling", self.channel_config_coupling)
        form.addRow("Bandwidth", self.channel_config_bandwidth)
        form.addRow("Invert", self.channel_config_invert)
        form.addRow("Probe gain", self.channel_config_probe_gain)

        hint = QLabel(
            "Blank optional fields are skipped. Bandwidth/probe options depend on scope firmware and probe type."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        form.addRow(hint)

        buttons = QHBoxLayout()
        buttons.addWidget(self._button("Read channel config", self.read_channel_configuration))
        buttons.addWidget(self._accent_button("Apply channel config", self.apply_channel_configuration))
        form.addRow(buttons)
        return self._prepare_channels_card(card)

    def _build_math_configuration_card(self):
        card = self._card("Math channel configuration")
        form = QFormLayout(card)
        self._prepare_form(form)

        self.math_config_display = QCheckBox("Show MATH waveform")
        self.math_config_define = QLineEdit("CH1+CH2")
        self.math_config_scale = QLineEdit("")
        self.math_config_position = QLineEdit("")

        form.addRow("Display", self.math_config_display)
        form.addRow("Define expression", self.math_config_define)
        form.addRow("Vertical scale", self.math_config_scale)
        form.addRow("Vertical position", self.math_config_position)

        hint = QLabel(
            "Uses MATH:DEFINE plus MATH:VERTICAL scale/position. Example expressions: CH1+CH2, CH1-CH2, CH1*CH2."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        form.addRow(hint)

        buttons = QHBoxLayout()
        buttons.addWidget(self._button("Read math config", self.read_math_configuration))
        buttons.addWidget(self._accent_button("Apply math config", self.apply_math_configuration))
        form.addRow(buttons)
        return self._prepare_channels_card(card)

    # ------------------------------------------------------------------
    # Public-driver channel and math actions
    # ------------------------------------------------------------------
    def _selected_config_channel(self) -> int:
        return int(self.channel_config_channel.currentText())

    @staticmethod
    def _bool_from_scope_response(text: str) -> bool:
        return bool_from_scope_response(text)

    @staticmethod
    def _set_combo_text(combo: QComboBox, text: str) -> None:
        if text:
            combo.setCurrentText(text)

    @staticmethod
    def _optional_text(value: str) -> str | None:
        text = str(value).strip()
        return text or None

    def read_channel_configuration(self) -> None:
        channel = self._selected_config_channel()
        result = self._run_action(
            f"Reading CH{channel} configuration",
            lambda scope: scope.get_channel_configuration(channel),
        )
        if isinstance(result, dict):
            self.channel_config_display.setChecked(self._bool_from_scope_response(result.get("display", "0")))
            self.channel_config_scale.setText(result.get("scale", ""))
            self.channel_config_position.setText(result.get("position", ""))
            self.channel_config_offset.setText(result.get("offset", ""))
            self._set_combo_text(self.channel_config_coupling, result.get("coupling", ""))
            self._set_combo_text(self.channel_config_bandwidth, result.get("bandwidth", ""))
            self.channel_config_invert.setChecked(self._bool_from_scope_response(result.get("invert", "0")))
            self.channel_config_probe_gain.setText(result.get("probe_gain", ""))

    def apply_channel_configuration(self) -> None:
        channel = self._selected_config_channel()
        config = ChannelConfig(
            channel=channel,
            display=self.channel_config_display.isChecked(),
            scale=self._optional_text(self.channel_config_scale.text()),
            position=self._optional_text(self.channel_config_position.text()),
            offset=self._optional_text(self.channel_config_offset.text()),
            coupling=self._optional_text(self.channel_config_coupling.currentText()),
            bandwidth=self._optional_text(self.channel_config_bandwidth.currentText()),
            invert=self.channel_config_invert.isChecked(),
            probe_gain=self._optional_text(self.channel_config_probe_gain.text()),
        )

        def action(scope):
            scope.configure_channel(config)
            return f"CH{channel} configuration applied"

        self._run_action(f"Applying CH{channel} configuration", action)

    def read_math_configuration(self) -> None:
        result = self._run_action(
            "Reading MATH configuration",
            lambda scope: scope.get_math_configuration(),
        )
        if isinstance(result, dict):
            self.math_config_display.setChecked(self._bool_from_scope_response(result.get("display", "0")))
            self.math_config_define.setText(result.get("define", ""))
            self.math_config_scale.setText(result.get("scale", ""))
            self.math_config_position.setText(result.get("position", ""))

    def apply_math_configuration(self) -> None:
        config = MathConfig(
            display=self.math_config_display.isChecked(),
            define=self._optional_text(self.math_config_define.text()),
            scale=self._optional_text(self.math_config_scale.text()),
            position=self._optional_text(self.math_config_position.text()),
        )

        def action(scope):
            scope.configure_math(config)
            return "MATH configuration applied"

        self._run_action("Applying MATH configuration", action)


__all__ = [
    "CHANNEL_CONFIG_FIELDS",
    "DRAWER_NAV_ICON_SIZE",
    "DRAWER_NAV_LABELS",
    "DRAWER_PAGE_ICON_NAMES",
    "MATH_CONFIG_FIELDS",
    "QtScopeWindow",
]
