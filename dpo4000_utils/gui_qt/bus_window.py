"""BUS1..BUS4 Channels-page extension for the launched DPO4000 Desk window."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
)

from ..bus import (
    BUS_DISPLAY_FORMATS,
    BUS_DISPLAY_TYPES,
    BUS_TYPES,
    BusConfig,
    bus_protocol_field_label,
    bus_protocol_fields,
    canonical_bus_type,
)
from .desktop_window import QtScopeWindow as DesktopQtScopeWindow

BUS_SCOPE_ACTIONS = {
    "read_bus_configuration",
    "apply_bus_configuration",
}


class QtScopeWindow(DesktopQtScopeWindow):
    """Final desktop window with DPO4000 BUS1..BUS4 configuration support."""

    def _build_connection_tab(self):
        """Add a persistent option controlling the automatic full scope readback."""
        page = super()._build_connection_tab()
        body = page.widget() if hasattr(page, "widget") else page
        layout = body.layout() if body is not None else None
        if layout is not None:
            card = self._card("Connection options")
            form = QFormLayout(card)
            self._prepare_form(form)

            self.read_all_parameters_after_connection = QCheckBox(
                "Read all parameters after connection"
            )
            self.read_all_parameters_after_connection.setChecked(True)
            form.addRow(self.read_all_parameters_after_connection)

            hint = QLabel(
                "Enabled: after a successful IDN test, read CH, MATH, REF, BUS, "
                "measurements, trigger, acquisition, and display settings. Disabled: "
                "stop after IDN for a faster connection test."
            )
            hint.setObjectName("MutedLabel")
            hint.setWordWrap(True)
            form.addRow(hint)

            insert_index = max(0, layout.count() - 1)
            layout.insertWidget(insert_index, card)
        return page

    def _apply_preferences(self, preferences) -> None:
        super()._apply_preferences(preferences)
        if hasattr(self, "read_all_parameters_after_connection"):
            self.read_all_parameters_after_connection.setChecked(
                preferences.read_all_parameters_after_connection
            )

    def _collect_preferences(self):
        preferences = super()._collect_preferences()
        if hasattr(self, "read_all_parameters_after_connection"):
            preferences.read_all_parameters_after_connection = (
                self.read_all_parameters_after_connection.isChecked()
            )
        return preferences

    def test_connection(self) -> None:
        """Run the normal IDN test while marking any following refresh as automatic."""
        self._connection_test_parameter_refresh = True
        try:
            super().test_connection()
        finally:
            self._connection_test_parameter_refresh = False

    def refresh_scope_parameters(self) -> None:
        """Skip only the automatic post-IDN refresh when the Connection option is off."""
        automatic_refresh = getattr(self, "_connection_test_parameter_refresh", False)
        read_all = getattr(self, "read_all_parameters_after_connection", None)
        if automatic_refresh and read_all is not None and not read_all.isChecked():
            self._last_action = "IDN OK; parameter read skipped"
            self._append_log("Full scope parameter read skipped by Connection setting")
            self._update_scope_control_enabled()
            self._update_status_strip()
            self.statusBar().showMessage(
                f"Connected: {self._last_idn} | parameter read skipped"
            )
            return
        super().refresh_scope_parameters()

    def _build_channels_tab(self):
        """Add the BUS card after the existing analog/MATH/REF controls."""
        page = super()._build_channels_tab()
        body = page.widget() if hasattr(page, "widget") else page
        layout = body.layout() if body is not None else None
        if layout is not None:
            insert_index = max(0, layout.count() - 1)
            layout.insertWidget(insert_index, self._build_bus_channel_card())
        return page

    def _build_bus_channel_card(self) -> QGroupBox:
        card = self._card("Bus channels")
        form = QFormLayout(card)
        self._prepare_form(form)

        self.bus_channel = QComboBox()
        self.bus_channel.addItems(["1", "2", "3", "4"])
        self.bus_state = QCheckBox("Show / enable selected bus")

        self.bus_type = QComboBox()
        self.bus_type.setEditable(True)
        self.bus_type.addItems(BUS_TYPES)

        self.bus_label = QLineEdit()
        self.bus_label.setMaxLength(30)
        self.bus_position = QLineEdit()

        self.bus_display_format = QComboBox()
        self.bus_display_format.setEditable(True)
        self.bus_display_format.addItems([""] + list(BUS_DISPLAY_FORMATS))

        self.bus_display_type = QComboBox()
        self.bus_display_type.setEditable(True)
        self.bus_display_type.addItems([""] + list(BUS_DISPLAY_TYPES))

        self.bus_protocol_table = QTableWidget(0, 2)
        self.bus_protocol_table.setHorizontalHeaderLabels(["Protocol setting", "Value"])
        self.bus_protocol_table.verticalHeader().setVisible(False)
        self.bus_protocol_table.setAlternatingRowColors(True)
        self.bus_protocol_table.setMinimumHeight(150)
        self.bus_protocol_table.setMaximumHeight(280)
        header = self.bus_protocol_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._bus_protocol_field_keys: list[str] = []

        form.addRow("Bus", self.bus_channel)
        form.addRow("State", self.bus_state)
        form.addRow("Type", self.bus_type)
        form.addRow("Label", self.bus_label)
        form.addRow("Position div", self.bus_position)
        form.addRow("Display format", self.bus_display_format)
        form.addRow("Display type", self.bus_display_type)
        form.addRow("Protocol setup", self.bus_protocol_table)

        hint = QLabel(
            "BUS1..BUS4 are option-dependent decoded bus waveforms. The protocol table "
            "covers the DPO4000 per-bus command set for I²C, SPI, CAN, RS-232/UART, "
            "LIN, FlexRay, Audio, USB, and Parallel. Parallel is MSO4000-only; other "
            "protocols require the corresponding application module. Unsupported "
            "settings are rejected by the oscilloscope."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        form.addRow(hint)

        buttons = QHBoxLayout()
        read_button = self._button("Read BUS", self.read_bus_configuration)
        apply_button = self._accent_button("Apply BUS", self.apply_bus_configuration)
        for button in (read_button, apply_button):
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            buttons.addWidget(button)
        form.addRow(buttons)

        self._populate_bus_protocol_table({})
        self.bus_type.currentTextChanged.connect(self._on_bus_type_changed)
        return self._prepare_channels_card(card)

    def _callback_requires_scope(self, callback) -> bool:
        if getattr(callback, "__name__", "") in BUS_SCOPE_ACTIONS:
            return True
        return super()._callback_requires_scope(callback)

    def _selected_bus_channel(self) -> int:
        return int(self.bus_channel.currentText())

    def _populate_bus_protocol_table(self, values: dict[str, Any]) -> None:
        bus_type = canonical_bus_type(self.bus_type.currentText())
        fields = list(bus_protocol_fields(bus_type))
        self._bus_protocol_field_keys = fields
        self.bus_protocol_table.setRowCount(len(fields))

        for row, field_name in enumerate(fields):
            label_item = QTableWidgetItem(bus_protocol_field_label(field_name))
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            label_item.setToolTip(field_name)
            value_item = QTableWidgetItem(str(values.get(field_name, "")))
            value_item.setToolTip(
                "Enter the enum, numeric value, or source token accepted by the oscilloscope."
            )
            self.bus_protocol_table.setItem(row, 0, label_item)
            self.bus_protocol_table.setItem(row, 1, value_item)

    def _on_bus_type_changed(self, _text: str) -> None:
        values: dict[str, Any] = {}
        snapshot = getattr(self, "_scope_parameter_snapshot", {})
        buses = snapshot.get("buses", {}) if isinstance(snapshot, dict) else {}
        try:
            bus = self._selected_bus_channel()
        except ValueError:
            self._populate_bus_protocol_table(values)
            return
        cached = buses.get(bus, {}) if isinstance(buses, dict) else {}
        if canonical_bus_type(cached.get("type", "")) == canonical_bus_type(
            self.bus_type.currentText()
        ):
            protocol = cached.get("protocol", {})
            if isinstance(protocol, dict):
                values = protocol
        self._populate_bus_protocol_table(values)

    def _bus_protocol_values_from_table(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for row, field_name in enumerate(self._bus_protocol_field_keys):
            item = self.bus_protocol_table.item(row, 1)
            text = item.text().strip() if item is not None else ""
            if text:
                values[field_name] = text
        return values

    def _bus_config_from_widgets(self) -> BusConfig:
        return BusConfig(
            bus=self._selected_bus_channel(),
            state=self.bus_state.isChecked(),
            bus_type=self.bus_type.currentText().strip() or None,
            label=self.bus_label.text(),
            position=self.bus_position.text().strip() or None,
            display_format=self.bus_display_format.currentText().strip() or None,
            display_type=self.bus_display_type.currentText().strip() or None,
            protocol_settings=self._bus_protocol_values_from_table(),
        )

    def _apply_bus_configuration_to_widgets(self, config: dict[str, Any]) -> None:
        self.bus_state.setChecked(self._bool_from_scope_response(config.get("state", "0")))
        bus_type = canonical_bus_type(str(config.get("type", "")))
        previous_block = self.bus_type.blockSignals(True)
        try:
            self._set_combo_text(self.bus_type, bus_type)
        finally:
            self.bus_type.blockSignals(previous_block)
        self.bus_label.setText(str(config.get("label", "")))
        self.bus_position.setText(str(config.get("position", "")))
        self._set_combo_text(self.bus_display_format, str(config.get("display_format", "")))
        self._set_combo_text(self.bus_display_type, str(config.get("display_type", "")))
        protocol = config.get("protocol", {})
        self._populate_bus_protocol_table(protocol if isinstance(protocol, dict) else {})

    def _cache_bus_configuration(self, bus: int, config: dict[str, Any]) -> None:
        snapshot = getattr(self, "_scope_parameter_snapshot", None)
        if not isinstance(snapshot, dict):
            snapshot = {}
            self._scope_parameter_snapshot = snapshot
        buses = snapshot.setdefault("buses", {})
        if isinstance(buses, dict):
            buses[int(bus)] = dict(config)

    def _apply_cached_bus_configuration(self, _text: str | None = None) -> None:
        if not hasattr(self, "bus_channel"):
            return
        snapshot = getattr(self, "_scope_parameter_snapshot", {})
        buses = snapshot.get("buses", {}) if isinstance(snapshot, dict) else {}
        try:
            bus = self._selected_bus_channel()
        except ValueError:
            return
        config = buses.get(bus, {}) if isinstance(buses, dict) else {}
        self._apply_bus_configuration_to_widgets(config or {})

    def read_bus_configuration(self) -> None:
        bus = self._selected_bus_channel()
        result = self._run_action(
            f"Reading BUS{bus} configuration",
            lambda scope: scope.get_bus_configuration(bus),
        )
        if isinstance(result, dict):
            self._cache_bus_configuration(bus, result)
            self._apply_bus_configuration_to_widgets(result)

    def apply_bus_configuration(self) -> None:
        config = self._bus_config_from_widgets()
        bus = config.bus

        def action(scope):
            scope.configure_bus(config)
            return scope.get_bus_configuration(bus)

        result = self._run_action(f"Applying BUS{bus} configuration", action)
        if isinstance(result, dict):
            self._cache_bus_configuration(bus, result)
            self._apply_bus_configuration_to_widgets(result)

    def _ensure_scope_parameter_pages_built(self) -> None:
        super()._ensure_scope_parameter_pages_built()
        if hasattr(self, "bus_channel") and not getattr(
            self, "_snapshot_bus_hook_installed", False
        ):
            self.bus_channel.currentTextChanged.connect(self._apply_cached_bus_configuration)
            self._snapshot_bus_hook_installed = True

    def _apply_scope_snapshot(self, snapshot: dict[str, Any]) -> None:
        super()._apply_scope_snapshot(snapshot)
        self._apply_cached_bus_configuration()


__all__ = ["BUS_SCOPE_ACTIONS", "QtScopeWindow"]
