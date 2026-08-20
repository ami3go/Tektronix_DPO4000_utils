"""Enhanced PySide6 window with full channel and math configuration controls."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .main_window import QtScopeWindow as BaseQtScopeWindow

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


class QtScopeWindow(BaseQtScopeWindow):
    """Qt window variant with full CH1..CH4 and MATH setup in Channels."""

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
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return card

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
    "MATH_CONFIG_FIELDS",
    "MATH_CONFIG_QUERIES",
    "QtScopeWindow",
]
