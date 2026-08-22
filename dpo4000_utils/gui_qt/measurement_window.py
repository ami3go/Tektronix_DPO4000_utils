"""Stable PySide6 window with existing measurement-slot management.

Adds a practical MEAS1..MEAS8 manager to the Measurement page.  The manager can
read the currently configured scope measurements, load an existing slot into the
normal editor, apply edits back to that slot, read its value, or disable/delete
that slot.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QGroupBox,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
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
MEASUREMENT_SETUP_QUERIES = {
    "state": "MEASUREMENT:MEAS{slot}:STATE?",
    "type": "MEASUREMENT:MEAS{slot}:TYPE?",
    "source1": "MEASUREMENT:MEAS{slot}:SOURCE1?",
    "source2": "MEASUREMENT:MEAS{slot}:SOURCE2?",
    "value": "MEASUREMENT:MEAS{slot}:VALUE?",
}
MEASUREMENT_TABLE_HEADERS = ("Slot", "State", "Type", "Source 1", "Source 2", "Value")
MEASUREMENT_MANAGER_BUTTON_MIN_HEIGHT = 38
MEASUREMENT_MANAGER_BUTTON_MIN_WIDTH = 150


class QtScopeWindow(DisplayQtScopeWindow):
    """Stable launched Qt window with editable existing measurement management."""

    def _build_preview_card(self) -> QGroupBox:
        """Keep the left preview card untitled so the toolbar and image use the space."""
        card = super()._build_preview_card()
        card.setTitle("")
        return card

    def _callback_requires_scope(self, callback) -> bool:
        """Gate measurement management actions behind the existing IDN safety check."""
        if getattr(callback, "__name__", "") in MEASUREMENT_MANAGEMENT_ACTIONS:
            return True
        return super()._callback_requires_scope(callback)

    def _build_measurement_tab(self) -> QWidget:
        """Add existing MEAS1..MEAS8 management above the normal measurement editor."""
        page = super()._build_measurement_tab()
        layout = page.layout()
        if layout is not None:
            layout.insertWidget(0, self._build_existing_measurements_card())
        return page

    def _build_existing_measurements_card(self) -> QGroupBox:
        card = self._card("Existing scope measurements")
        layout = QVBoxLayout(card)
        layout.setSpacing(10)

        hint = QLabel(
            "Read MEAS1..MEAS8 from the scope, select a row, then load/edit/delete that slot. "
            "Edits use the normal Measurement editor below."
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
        self.existing_measurements.itemDoubleClicked.connect(
            lambda _item: self.load_selected_measurement_for_edit()
        )
        layout.addWidget(self.existing_measurements)
        self._reset_existing_measurements_table()

        layout.addWidget(self._build_existing_measurements_actions())
        return self._prepare_drawer_card(card)

    def _build_existing_measurements_actions(self) -> QWidget:
        """Build large action buttons that remain usable in the narrow right panel."""
        actions = QWidget()
        actions.setObjectName("MeasurementManagerActions")
        grid = QGridLayout(actions)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        button_specs = (
            (self._button("Read configured", self.read_existing_measurements), 0, 0, 1, 1),
            (self._button("Load selected", self.load_selected_measurement_for_edit), 0, 1, 1, 1),
            (self._accent_button("Apply edit", self.apply_selected_measurement_edit), 1, 0, 1, 1),
            (self._button("Read value", self.read_selected_measurement_value), 1, 1, 1, 1),
            (self._button("Delete selected", self.delete_selected_measurement), 2, 0, 1, 2),
        )
        for button, row, column, row_span, column_span in button_specs:
            button.setMinimumHeight(MEASUREMENT_MANAGER_BUTTON_MIN_HEIGHT)
            button.setMinimumWidth(MEASUREMENT_MANAGER_BUTTON_MIN_WIDTH)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            grid.addWidget(button, row, column, row_span, column_span)
        return actions

    def _reset_existing_measurements_table(self) -> None:
        for row, slot in enumerate(MEASUREMENT_SLOTS):
            self._set_measurement_table_row(
                row,
                {
                    "slot": str(slot),
                    "state": "Unknown",
                    "type": "",
                    "source1": "",
                    "source2": "",
                    "value": "",
                },
            )

    def _set_measurement_table_row(self, row: int, data: dict[str, Any]) -> None:
        values = (
            f"MEAS{data.get('slot', row + 1)}",
            str(data.get("state", "")),
            str(data.get("type", "")),
            str(data.get("source1", "")),
            str(data.get("source2", "")),
            str(data.get("value", "")),
        )
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

    @staticmethod
    def _normalise_scope_text(text: str) -> str:
        value = str(text or "").strip()
        if "\"" in value:
            return value.split("\"", 1)[1].rsplit("\"", 1)[0]
        return value.split()[-1] if value.split() else ""

    def _set_measurement_editor(
        self,
        *,
        slot: int,
        measurement_type: str,
        source1: str,
        source2: str,
    ) -> None:
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
        return MeasurementConfig(
            slot=slot,
            measurement_type=self.measurement_type.currentText(),
            source1=self.measurement_source1.currentText(),
            source2=self.measurement_source2.currentText() or None,
        )

    def read_existing_measurements(self) -> None:
        def action(scope) -> dict[int, dict[str, str]]:
            instrument = getattr(scope, "scope", None)
            if instrument is None:
                raise ConnectionError("Oscilloscope is not connected.")
            result: dict[int, dict[str, str]] = {}
            for slot in MEASUREMENT_SLOTS:
                slot_result = {
                    name: self._query_optional(instrument, query.format(slot=slot))
                    for name, query in MEASUREMENT_SETUP_QUERIES.items()
                }
                result[slot] = {name: self._normalise_scope_text(value) for name, value in slot_result.items()}
            return result

        result = self._run_action("Reading existing measurement setup", action)
        if isinstance(result, dict):
            for slot, values in result.items():
                row = self._measurement_row_for_slot(int(slot))
                state = "ON" if self._bool_from_scope_response(values.get("state", "0")) else "OFF"
                self._set_measurement_table_row(
                    row,
                    {
                        "slot": str(slot),
                        "state": state,
                        "type": values.get("type", ""),
                        "source1": values.get("source1", ""),
                        "source2": values.get("source2", ""),
                        "value": values.get("value", ""),
                    },
                )

    def load_selected_measurement_for_edit(self) -> None:
        slot = self._selected_existing_measurement_slot()
        row = self._measurement_row_for_slot(slot)
        table = self.existing_measurements
        measurement_type = table.item(row, 2).text() if table.item(row, 2) is not None else ""
        source1 = table.item(row, 3).text() if table.item(row, 3) is not None else ""
        source2 = table.item(row, 4).text() if table.item(row, 4) is not None else ""
        self._set_measurement_editor(
            slot=slot,
            measurement_type=measurement_type,
            source1=source1 or "CH1",
            source2=source2,
        )
        self.statusBar().showMessage(f"Loaded MEAS{slot} into editor")

    def apply_selected_measurement_edit(self) -> None:
        slot = self._selected_existing_measurement_slot()
        config = self._selected_measurement_config_for_slot(slot)

        def action(scope) -> dict[str, str]:
            scope.add_measurement(config)
            instrument = getattr(scope, "scope", None)
            if instrument is None:
                raise ConnectionError("Oscilloscope is not connected.")
            return {
                name: self._normalise_scope_text(self._query_optional(instrument, query.format(slot=slot)))
                for name, query in MEASUREMENT_SETUP_QUERIES.items()
            }

        result = self._run_action(f"Applying edit to MEAS{slot}", action)
        if isinstance(result, dict):
            row = self._measurement_row_for_slot(slot)
            self._set_measurement_table_row(
                row,
                {
                    "slot": str(slot),
                    "state": "ON" if self._bool_from_scope_response(result.get("state", "1")) else "OFF",
                    "type": result.get("type", config.measurement_type),
                    "source1": result.get("source1", config.source1),
                    "source2": result.get("source2", config.source2 or ""),
                    "value": result.get("value", ""),
                },
            )

    def delete_selected_measurement(self) -> None:
        slot = self._selected_existing_measurement_slot()
        result = self._run_action(f"Deleting MEAS{slot}", lambda scope: scope.disable_measurement(slot))
        if result is not None or self._connection_ok:
            row = self._measurement_row_for_slot(slot)
            self._set_measurement_table_row(
                row,
                {"slot": str(slot), "state": "OFF", "type": "", "source1": "", "source2": "", "value": ""},
            )
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


__all__ = [
    "MEASUREMENT_MANAGEMENT_ACTIONS",
    "MEASUREMENT_MANAGER_BUTTON_MIN_HEIGHT",
    "MEASUREMENT_MANAGER_BUTTON_MIN_WIDTH",
    "MEASUREMENT_SETUP_QUERIES",
    "MEASUREMENT_TABLE_HEADERS",
    "QtScopeWindow",
]
