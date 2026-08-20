"""Enhanced PySide6 window with full channel and math configuration controls."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
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
CHANNEL_CONFIG_QUERIES = {
    "display": "SELECT:CH{channel}?",
    "scale": "CH{channel}:SCALE?",
    "position": "CH{channel}:POSITION?",
    "offset": "CH{channel}:OFFSET?",
    "coupling": "CH{channel}:COUPLING?",
    "bandwidth": "CH{channel}:BANDWIDTH?",
    "invert": "CH{channel}:INVERT?",
    "probe_gain": "CH{channel}:PROBE:GAIN?",
}
MATH_CONFIG_QUERIES = {
    "display": "SELECT:MATH?",
    "define": "MATH:DEFINE?",
    "scale": "MATH:VERTICAL:SCALE?",
    "position": "MATH:VERTICAL:POSITION?",
}
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
    """Qt window variant with full CH1..CH4 and MATH setup in Channels."""

    def _build_preview_card(self):
        """Build preview card and restore Ctrl+C copy behavior when preview has focus."""
        card = super()._build_preview_card()
        card.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        card.setToolTip("Click the screen preview, then press Ctrl+C to copy the current image.")
        self.preview_label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.preview_label.setToolTip("Click here, then press Ctrl+C to copy the current image.")
        self.preview_copy_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Copy), card)
        self.preview_copy_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.preview_copy_shortcut.activated.connect(self.copy_preview)
        return card

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

    def _build_trigger_tab(self) -> QWidget:
        """Build trigger page inside a scroll area so cards never collapse."""
        body = super()._build_trigger_tab()
        return self._wrap_scrollable_drawer_page(
            body,
            scroll_name="TriggerScrollArea",
            body_name="TriggerScrollBody",
        )

    def _build_channels_tab(self) -> QWidget:
        body = QWidget()
        body.setObjectName("ChannelsScrollBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_channel_labels_card())
        layout.addWidget(self._build_channel_configuration_card())
        layout.addWidget(self._build_math_configuration_card())
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setObjectName("ChannelsScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        return scroll

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

    def _selected_config_channel(self) -> int:
        return int(self.channel_config_channel.currentText())

    @staticmethod
    def _bool_from_scope_response(text: str) -> bool:
        tokens = str(text).strip().upper().split()
        if not tokens:
            return False
        return tokens[-1] not in {"0", "OFF", "FALSE"}

    @staticmethod
    def _query_optional(instrument: Any, command: str) -> str:
        try:
            response = instrument.query(command).strip()
        except Exception:
            return ""
        if "\"" in response:
            return response.split("\"", 1)[1].rsplit("\"", 1)[0]
        return response.split()[-1] if response.split() else response

    @staticmethod
    def _set_combo_text(combo: QComboBox, text: str) -> None:
        if text:
            combo.setCurrentText(text)

    @staticmethod
    def _write_if_text(instrument: Any, command_prefix: str, value: str) -> None:
        text = str(value).strip()
        if text:
            instrument.write(f"{command_prefix} {text}")

    @staticmethod
    def _quote_math_expression(expression: str) -> str:
        return expression.strip().replace('"', "'")

    def read_channel_configuration(self) -> None:
        channel = self._selected_config_channel()

        def action(scope):
            instrument = getattr(scope, "scope", None)
            if instrument is None:
                raise ConnectionError("Oscilloscope is not connected.")
            return {
                name: self._query_optional(instrument, query.format(channel=channel))
                for name, query in CHANNEL_CONFIG_QUERIES.items()
            }

        result = self._run_action(f"Reading CH{channel} configuration", action)
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
        display = self.channel_config_display.isChecked()
        invert = self.channel_config_invert.isChecked()
        scale = self.channel_config_scale.text()
        position = self.channel_config_position.text()
        offset = self.channel_config_offset.text()
        coupling = self.channel_config_coupling.currentText()
        bandwidth = self.channel_config_bandwidth.currentText()
        probe_gain = self.channel_config_probe_gain.text()

        def action(scope):
            instrument = getattr(scope, "scope", None)
            if instrument is None:
                raise ConnectionError("Oscilloscope is not connected.")
            instrument.write(f"SELECT:CH{channel} {'ON' if display else 'OFF'}")
            self._write_if_text(instrument, f"CH{channel}:SCALE", scale)
            self._write_if_text(instrument, f"CH{channel}:POSITION", position)
            self._write_if_text(instrument, f"CH{channel}:OFFSET", offset)
            self._write_if_text(instrument, f"CH{channel}:COUPLING", coupling)
            self._write_if_text(instrument, f"CH{channel}:BANDWIDTH", bandwidth)
            instrument.write(f"CH{channel}:INVERT {'ON' if invert else 'OFF'}")
            self._write_if_text(instrument, f"CH{channel}:PROBE:GAIN", probe_gain)
            return f"CH{channel} configuration applied"

        self._run_action(f"Applying CH{channel} configuration", action)

    def read_math_configuration(self) -> None:
        def action(scope):
            instrument = getattr(scope, "scope", None)
            if instrument is None:
                raise ConnectionError("Oscilloscope is not connected.")
            return {name: self._query_optional(instrument, query) for name, query in MATH_CONFIG_QUERIES.items()}

        result = self._run_action("Reading MATH configuration", action)
        if isinstance(result, dict):
            self.math_config_display.setChecked(self._bool_from_scope_response(result.get("display", "0")))
            self.math_config_define.setText(result.get("define", ""))
            self.math_config_scale.setText(result.get("scale", ""))
            self.math_config_position.setText(result.get("position", ""))

    def apply_math_configuration(self) -> None:
        display = self.math_config_display.isChecked()
        expression = self._quote_math_expression(self.math_config_define.text())
        scale = self.math_config_scale.text()
        position = self.math_config_position.text()

        def action(scope):
            instrument = getattr(scope, "scope", None)
            if instrument is None:
                raise ConnectionError("Oscilloscope is not connected.")
            if expression:
                instrument.write(f'MATH:DEFINE "{expression}"')
            self._write_if_text(instrument, "MATH:VERTICAL:SCALE", scale)
            self._write_if_text(instrument, "MATH:VERTICAL:POSITION", position)
            instrument.write(f"SELECT:MATH {'ON' if display else 'OFF'}")
            return "MATH configuration applied"

        self._run_action("Applying MATH configuration", action)


__all__ = [
    "CHANNEL_CONFIG_FIELDS",
    "CHANNEL_CONFIG_QUERIES",
    "DRAWER_NAV_ICON_SIZE",
    "DRAWER_NAV_LABELS",
    "DRAWER_PAGE_ICON_NAMES",
    "MATH_CONFIG_FIELDS",
    "MATH_CONFIG_QUERIES",
    "QtScopeWindow",
]
