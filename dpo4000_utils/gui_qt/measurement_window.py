"""Stable PySide6 window with existing measurement-slot management.

Adds a practical MEAS1..MEAS8 manager to the Measurement page. The manager can
read the currently configured scope measurements, load an existing slot into the
normal editor, apply edits back to that slot, read its value, or disable/delete
that slot. Destructive/edit actions are locked behind an explicit pencil edit
mode to prevent accidental measurement changes.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..control import MEASUREMENT_SLOTS, MEASUREMENT_TYPES_BY_GROUP, MeasurementConfig
from .display_window import QtScopeWindow as DisplayQtScopeWindow

MEASUREMENT_MANAGEMENT_ACTIONS = {
    "read_existing_measurements",
    "apply_selected_measurement_edit",
    "delete_selected_measurement",
    "read_selected_measurement_value",
}
MEASUREMENT_TABLE_HEADERS = ("Slot", "State", "Type", "Source 1", "Source 2", "Value")
MEASUREMENT_MANAGER_BUTTON_MIN_HEIGHT = 38
MEASUREMENT_MANAGER_BUTTON_MIN_WIDTH = 150
MEASUREMENT_EDIT_MODE_ICON = "✎"
MEASUREMENT_EDIT_MODE_LOCKED_TEXT = "Editing locked"
MEASUREMENT_EDIT_MODE_ENABLED_TEXT = "Editing enabled"


class QtScopeWindow(DisplayQtScopeWindow):
    """Stable launched Qt window with editable existing measurement management."""

    def _build_preview_card(self) -> QGroupBox:
        card = super()._build_preview_card()
        card.setTitle("")
        return card

    def _callback_requires_scope(self, callback) -> bool:
        if getattr(callback, "__name__", "") in MEASUREMENT_MANAGEMENT_ACTIONS:
            return True
        return super()._callback_requires_scope(callback)

    def _build_measurement_tab(self) -> QWidget:
        page = super()._build_measurement_tab()
        layout = page.layout()
        if layout is not None:
            layout.insertWidget(0, self._build_existing_measurements_card())
        return page

    def _build_existing_measurements_card(self) -> QGroupBox:
        card = self._card("Existing scope measurements")
        layout = QVBoxLayout(card)
        layout.setSpacing(10)
        self._measurement_edit_mode_enabled = False
        layout.addWidget(self._build_measurement_edit_mode_header())
        hint = QLabel(
            "Read MEAS1..MEAS8 from the scope, select a row, then load that slot into the "
            "normal Measurement editor below. Turn on pencil Edit mode before applying edits "
            "or deleting a measurement."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.existing_measurements = QTableWidget(len(MEASUREMENT_SLOTS), len(MEASUREMENT_TABLE_HEADERS))
        self.existing_measurements.setObjectName("ExistingMeasurementsTable")
        self.existing_measurements.setHorizontalHeaderLabels(MEASUREMENT_TABLE_HEADERS)
        self.existing_measurements.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.existing_measurements.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.existing_measurements.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.existing_measurements.verticalHeader().setVisible(False)
        self.existing_measurements.setAlternatingRowColors(True)
        self.existing_measurements.setMinimumHeight(210)
        self.existing_measurements.itemDoubleClicked.connect(lambda _item: self.load_selected_measurement_for_edit())
        layout.addWidget(self.existing_measurements)
        self._reset_existing_measurements_table()
        layout.addWidget(self._build_existing_measurements_actions())
        self._set_measurement_edit_mode(False, announce=False)
        return self._prepare_drawer_card(card)

    def _build_measurement_edit_mode_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("MeasurementEditModeHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.measurement_edit_mode_state = QLabel(MEASUREMENT_EDIT_MODE_LOCKED_TEXT)
        self.measurement_edit_mode_state.setObjectName("MeasurementEditModeState")
        self.measurement_edit_mode_state.setToolTip("Apply edit and Delete selected are disabled until edit mode is enabled.")
        layout.addWidget(self.measurement_edit_mode_state)
        layout.addStretch(1)
        self.measurement_edit_mode_button = QToolButton()
        self.measurement_edit_mode_button.setObjectName("MeasurementEditModeButton")
        self.measurement_edit_mode_button.setText(f"{MEASUREMENT_EDIT_MODE_ICON} Edit")
        self.measurement_edit_mode_button.setCheckable(True)
        self.measurement_edit_mode_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.measurement_edit_mode_button.setToolTip("Enable Apply edit and Delete selected for the selected MEAS slot.")
        self.measurement_edit_mode_button.clicked.connect(self.toggle_measurement_edit_mode)
        layout.addWidget(self.measurement_edit_mode_button, 0, Qt.AlignmentFlag.AlignRight)
        return header

    def _build_existing_measurements_actions(self) -> QWidget:
        actions = QWidget()
        actions.setObjectName("MeasurementManagerActions")
        grid = QGridLayout(actions)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self.read_existing_measurements_button = self._button("Read configured", self.read_existing_measurements)
        self.load_selected_measurement_button = self._button("Load selected", self.load_selected_measurement_for_edit)
        self.apply_measurement_edit_button = self._accent_button("Apply edit", self.apply_selected_measurement_edit)
        self.read_selected_measurement_value_button = self._button("Read value", self.read_selected_measurement_value)
        self.delete_measurement_button = self._button("Delete selected", self.delete_selected_measurement)
        button_specs = (
            (self.read_existing_measurements_button, 0, 0, 1, 1),
            (self.load_selected_measurement_button, 0, 1, 1, 1),
            (self.apply_measurement_edit_button, 1, 0, 1, 1),
            (self.read_selected_measurement_value_button, 1, 1, 1, 1),
            (self.delete_measurement_button, 2, 0, 1, 2),
        )
        for button, row, column, row_span, column_span in button_specs:
            button.setMinimumHeight(MEASUREMENT_MANAGER_BUTTON_MIN_HEIGHT)
            button.setMinimumWidth(MEASUREMENT_MANAGER_BUTTON_MIN_WIDTH)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            grid.addWidget(button, row, column, row_span, column_span)
        return actions

    def toggle_measurement_edit_mode(self, checked: bool) -> None:
        self._set_measurement_edit_mode(bool(checked))

    def _set_measurement_edit_mode(self, enabled: bool, *, announce: bool = True) -> None:
        self._measurement_edit_mode_enabled = bool(enabled)
        button = getattr(self, "measurement_edit_mode_button", None)
        if button is not None:
            button.setChecked(self._measurement_edit_mode_enabled)
            button.setText(f"{MEASUREMENT_EDIT_MODE_ICON} Edit on" if self._measurement_edit_mode_enabled else f"{MEASUREMENT_EDIT_MODE_ICON} Edit")
            button.setToolTip("Lock Apply edit and Delete selected." if self._measurement_edit_mode_enabled else "Enable Apply edit and Delete selected for the selected MEAS slot.")
        state = getattr(self, "measurement_edit_mode_state", None)
        if state is not None:
            state.setText(MEASUREMENT_EDIT_MODE_ENABLED_TEXT if self._measurement_edit_mode_enabled else MEASUREMENT_EDIT_MODE_LOCKED_TEXT)
        for guarded_button_name in ("apply_measurement_edit_button", "delete_measurement_button"):
            guarded_button = getattr(self, guarded_button_name, None)
            if guarded_button is not None:
                guarded_button.setEnabled(self._measurement_edit_mode_enabled)
        if announce:
            self.statusBar().showMessage("Measurement edit mode enabled" if self._measurement_edit_mode_enabled else "Measurement edit mode locked")

    def _measurement_edit_mode_is_enabled(self) -> bool:
        return bool(getattr(self, "_measurement_edit_mode_enabled", False))

    def _guard_measurement_edit_mode(self) -> bool:
        if self._measurement_edit_mode_is_enabled():
            return True
        self.statusBar().showMessage("Turn on pencil Edit mode before applying edits or deleting measurements")
        return False

    def _reset_existing_measurements_table(self) -> None:
        for row, slot in enumerate(MEASUREMENT_SLOTS):
            self._set_measurement_table_row(row, {"slot": str(slot), "state": "Unknown", "type": "", "source1": "", "source2": "", "value": ""})

    def _set_measurement_table_row(self, row: int, data: dict[str, Any]) -> None:
        values = (f"MEAS{data.get('slot', row + 1)}", str(data.get("state", "")), str(data.get("type", "")), str(data.get("source1", "")), str(data.get("source2", "")), str(data.get("value", "")))
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.existing_measurements.setItem(row, column, item)
        self.existing_measurements.resizeColumnsToContents()

    def _selected_existing_measurement_slot(self) -> int:
        table = getattr(self, "existing_measurements", None)
        if table is not None:
            selected = table.selectedRanges()
            if selected:
                row = selected[0].topRow()
                item = table.item(row, 0)
                if item is not None:
                    text = item.text().strip().upper().replace("MEAS", "")
                    try:
                        return int(text)
                    except ValueError:
                        pass
        return int(self.measurement_slot.currentText())

    def _measurement_row_for_slot(self, slot: int) -> int:
        return max(0, min(len(MEASUREMENT_SLOTS) - 1, int(slot) - 1))

    def _set_measurement_editor(self, *, slot: int, measurement_type: str, source1: str, source2: str) -> None:
        self._set_combo_text(self.measurement_slot, str(slot))
        normal_type = measurement_type.strip().upper()
        for group, values in MEASUREMENT_TYPES_BY_GROUP.items():
            if normal_type in values:
                self._set_combo_text(self.measurement_group, group)
                self._update_measurement_types(group)
                break
        self._set_combo_text(self.measurement_type, normal_type)
        self._set_combo_text(self.measurement_source1, source1.strip().upper())
        self._set_combo_text(self.measurement_source2, source2.strip().upper())

    def _selected_measurement_config_for_slot(self, slot: int) -> MeasurementConfig:
        return MeasurementConfig(slot=slot, measurement_type=self.measurement_type.currentText(), source1=self.measurement_source1.currentText(), source2=self.measurement_source2.currentText() or None)

    @staticmethod
    def _measurement_setup_to_dict(setup) -> dict[str, str]:
        return {"slot": str(setup.slot), "state": str(setup.state), "type": str(setup.measurement_type), "source1": str(setup.source1), "source2": str(setup.source2), "value": str(setup.value)}

    def read_existing_measurements(self) -> None:
        result = self._run_action("Reading existing measurement setup", lambda scope: scope.get_all_measurement_setups())
        if isinstance(result, dict):
            for slot, setup in result.items():
                self._set_measurement_table_row(self._measurement_row_for_slot(int(slot)), self._measurement_setup_to_dict(setup))

    def load_selected_measurement_for_edit(self) -> None:
        slot = self._selected_existing_measurement_slot()
        row = self._measurement_row_for_slot(slot)
        table = self.existing_measurements
        measurement_type = table.item(row, 2).text() if table.item(row, 2) is not None else ""
        source1 = table.item(row, 3).text() if table.item(row, 3) is not None else ""
        source2 = table.item(row, 4).text() if table.item(row, 4) is not None else ""
        self._set_measurement_editor(slot=slot, measurement_type=measurement_type, source1=source1 or "CH1", source2=source2)
        self.statusBar().showMessage(f"Loaded MEAS{slot} into editor")

    def apply_selected_measurement_edit(self) -> None:
        if not self._guard_measurement_edit_mode():
            return
        slot = self._selected_existing_measurement_slot()
        config = self._selected_measurement_config_for_slot(slot)
        def action(scope):
            scope.add_measurement(config)
            return scope.get_measurement_setup(slot)
        result = self._run_action(f"Applying edit to MEAS{slot}", action)
        if result is not None:
            self._set_measurement_table_row(self._measurement_row_for_slot(slot), self._measurement_setup_to_dict(result))

    def delete_selected_measurement(self) -> None:
        if not self._guard_measurement_edit_mode():
            return
        slot = self._selected_existing_measurement_slot()
        result = self._run_action(f"Deleting MEAS{slot}", lambda scope: scope.disable_measurement(slot))
        if result is not None or getattr(self, "_connection_ok", False):
            self._set_measurement_table_row(self._measurement_row_for_slot(slot), {"slot": str(slot), "state": "OFF", "type": "", "source1": "", "source2": "", "value": ""})
            if int(self.measurement_slot.currentText()) == slot:
                self.measurement_value.clear()

    def read_selected_measurement_value(self) -> None:
        slot = self._selected_existing_measurement_slot()
        result = self._run_action(f"Reading MEAS{slot} value", lambda scope: scope.read_measurement_value(slot))
        if result is not None:
            text = str(result)
            self.measurement_value.setText(text)
            row = self._measurement_row_for_slot(slot)
            for column, value in ((1, "ON"), (5, text)):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.existing_measurements.setItem(row, column, item)
            self.existing_measurements.resizeColumnsToContents()


__all__ = ["MEASUREMENT_EDIT_MODE_ENABLED_TEXT", "MEASUREMENT_EDIT_MODE_ICON", "MEASUREMENT_EDIT_MODE_LOCKED_TEXT", "MEASUREMENT_MANAGEMENT_ACTIONS", "MEASUREMENT_MANAGER_BUTTON_MIN_HEIGHT", "MEASUREMENT_MANAGER_BUTTON_MIN_WIDTH", "MEASUREMENT_TABLE_HEADERS", "QtScopeWindow"]
