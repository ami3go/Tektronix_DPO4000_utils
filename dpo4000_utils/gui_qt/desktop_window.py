"""Final desktop presentation policy for DPO4000 Desk.

This layer specializes the API-only Qt window with non-modal connection feedback,
a post-connection state refresh, and reference-waveform controls. Instrument reads
are collected through the public driver API in one session and projected into the
already-built Qt cards.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSizePolicy,
)

from ..reference import REFERENCE_SOURCES, ReferenceConfig
from ..scope_snapshot import read_scope_snapshot
from .api_window import QtScopeWindow as ApiQtScopeWindow, _record_length_display

CONNECTION_TEST_DESCRIPTION = "Testing scope connection"
SCOPE_REFRESH_DESCRIPTION = "Reading scope parameters"
NON_MODAL_CONNECTION_ACTIONS = {CONNECTION_TEST_DESCRIPTION, SCOPE_REFRESH_DESCRIPTION}
REFERENCE_SCOPE_ACTIONS = {
    "read_reference_configuration",
    "apply_reference_configuration",
    "store_reference_waveform",
}


class QtScopeWindow(ApiQtScopeWindow):
    """Launched desktop window with status-only connection feedback."""

    # ------------------------------------------------------------------
    # Channels page extension: REF1..REF4
    # ------------------------------------------------------------------
    def _build_channels_tab(self):
        """Add reference-waveform controls to the existing Channels page."""
        page = super()._build_channels_tab()
        body = page.widget() if hasattr(page, "widget") else page
        layout = body.layout() if body is not None else None
        if layout is not None:
            insert_index = max(0, layout.count() - 1)
            layout.insertWidget(insert_index, self._build_reference_waveform_card())
        return page

    def _build_reference_waveform_card(self) -> QGroupBox:
        card = self._card("Reference waveforms")
        form = QFormLayout(card)
        self._prepare_form(form)

        self.reference_channel = QComboBox()
        self.reference_channel.addItems(["1", "2", "3", "4"])

        self.reference_display = QCheckBox("Show selected reference waveform")
        self.reference_label = QLineEdit()
        self.reference_label.setMaxLength(30)
        self.reference_vertical_scale = QLineEdit()
        self.reference_vertical_position = QLineEdit()
        self.reference_horizontal_scale = QLineEdit()
        self.reference_horizontal_delay = QLineEdit()

        self.reference_stored_at = QLineEdit()
        self.reference_stored_at.setReadOnly(True)

        self.reference_source = QComboBox()
        self.reference_source.addItems(REFERENCE_SOURCES)

        form.addRow("Reference", self.reference_channel)
        form.addRow("Display", self.reference_display)
        form.addRow("Label", self.reference_label)
        form.addRow("Vertical scale / div", self.reference_vertical_scale)
        form.addRow("Vertical position div", self.reference_vertical_position)
        form.addRow("Horizontal scale s/div", self.reference_horizontal_scale)
        form.addRow("Horizontal delay s", self.reference_horizontal_delay)
        form.addRow("Stored date / time", self.reference_stored_at)
        form.addRow("Store waveform source", self.reference_source)

        hint = QLabel(
            "REF1..REF4 are nonvolatile reference memories. Display scale/position "
            "changes only the reference trace. Storing a waveform overwrites the "
            "selected reference memory."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        form.addRow(hint)

        read_apply = QHBoxLayout()
        read_button = self._button("Read REF", self.read_reference_configuration)
        apply_button = self._accent_button("Apply REF", self.apply_reference_configuration)
        for button in (read_button, apply_button):
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            read_apply.addWidget(button)
        form.addRow(read_apply)

        store_button = self._accent_button(
            "Store source → selected REF",
            self.store_reference_waveform,
        )
        store_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form.addRow(store_button)

        return self._prepare_channels_card(card)

    def _callback_requires_scope(self, callback) -> bool:
        if getattr(callback, "__name__", "") in REFERENCE_SCOPE_ACTIONS:
            return True
        return super()._callback_requires_scope(callback)

    def _selected_reference_channel(self) -> int:
        return int(self.reference_channel.currentText())

    def _reference_config_from_widgets(self) -> ReferenceConfig:
        return ReferenceConfig(
            reference=self._selected_reference_channel(),
            display=self.reference_display.isChecked(),
            label=self.reference_label.text(),
            vertical_scale=self.reference_vertical_scale.text().strip() or None,
            vertical_position=self.reference_vertical_position.text().strip() or None,
            horizontal_scale=self.reference_horizontal_scale.text().strip() or None,
            horizontal_delay=self.reference_horizontal_delay.text().strip() or None,
        )

    def _apply_reference_configuration_to_widgets(self, config: dict[str, Any]) -> None:
        self.reference_display.setChecked(
            self._bool_from_scope_response(config.get("display", "0"))
        )
        self.reference_label.setText(str(config.get("label", "")))
        self.reference_vertical_scale.setText(str(config.get("vertical_scale", "")))
        self.reference_vertical_position.setText(str(config.get("vertical_position", "")))
        self.reference_horizontal_scale.setText(str(config.get("horizontal_scale", "")))
        self.reference_horizontal_delay.setText(str(config.get("horizontal_delay", "")))

        date = str(config.get("date", "")).strip()
        time = str(config.get("time", "")).strip()
        self.reference_stored_at.setText(" ".join(part for part in (date, time) if part))

    def _cache_reference_configuration(
        self,
        reference: int,
        config: dict[str, Any],
    ) -> None:
        snapshot = getattr(self, "_scope_parameter_snapshot", None)
        if not isinstance(snapshot, dict):
            snapshot = {}
            self._scope_parameter_snapshot = snapshot
        references = snapshot.setdefault("references", {})
        if isinstance(references, dict):
            references[int(reference)] = dict(config)

    def _apply_cached_reference_configuration(self, _text: str | None = None) -> None:
        if not hasattr(self, "reference_channel"):
            return
        snapshot = getattr(self, "_scope_parameter_snapshot", {})
        references = snapshot.get("references", {}) if isinstance(snapshot, dict) else {}
        try:
            reference = self._selected_reference_channel()
        except ValueError:
            return
        config = references.get(reference, {}) if isinstance(references, dict) else {}
        self._apply_reference_configuration_to_widgets(config or {})

    def read_reference_configuration(self) -> None:
        reference = self._selected_reference_channel()
        result = self._run_action(
            f"Reading REF{reference} configuration",
            lambda scope: scope.get_reference_configuration(reference),
        )
        if isinstance(result, dict):
            self._cache_reference_configuration(reference, result)
            self._apply_reference_configuration_to_widgets(result)

    def apply_reference_configuration(self) -> None:
        config = self._reference_config_from_widgets()
        reference = config.reference

        def action(scope):
            scope.configure_reference(config)
            return scope.get_reference_configuration(reference)

        result = self._run_action(
            f"Applying REF{reference} configuration",
            action,
        )
        if isinstance(result, dict):
            self._cache_reference_configuration(reference, result)
            self._apply_reference_configuration_to_widgets(result)

    def store_reference_waveform(self) -> None:
        reference = self._selected_reference_channel()
        source = self.reference_source.currentText().strip().upper()
        if source == f"REF{reference}":
            self.statusBar().showMessage(
                f"Cannot copy REF{reference} into itself; choose another source"
            )
            return

        answer = QMessageBox.question(
            self,
            "Overwrite reference waveform",
            (
                f"Store {source} into REF{reference}?\n\n"
                f"The existing REF{reference} waveform will be overwritten."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.statusBar().showMessage("Reference waveform store cancelled")
            return

        def action(scope):
            scope.save_waveform_to_reference(source, reference)
            return scope.get_reference_configuration(reference)

        result = self._run_action(
            f"Storing {source} in REF{reference}",
            action,
        )
        if isinstance(result, dict):
            self._cache_reference_configuration(reference, result)
            self._apply_reference_configuration_to_widgets(result)

    # ------------------------------------------------------------------
    # Connection and automatic live-state refresh
    # ------------------------------------------------------------------
    def test_connection(self) -> None:
        """Test the selected scope, then replace card defaults with live scope values."""
        result = self._run_action(
            CONNECTION_TEST_DESCRIPTION,
            lambda scope: scope.query_identity(),
        )
        if result is None:
            return

        idn = str(result).strip()
        self._last_idn = idn
        self._connection_ok = True
        self._last_action = "IDN OK"
        self._update_scope_control_enabled()
        self._update_status_strip()
        self.statusBar().showMessage(f"Connected: {idn}")
        self.refresh_scope_parameters()

    def refresh_scope_parameters(self) -> None:
        """Read all instrument-backed cards through one short-lived scope session."""
        self._ensure_scope_parameter_pages_built()
        result = self._run_action(
            SCOPE_REFRESH_DESCRIPTION,
            lambda scope: read_scope_snapshot(scope),
        )
        if not isinstance(result, dict):
            return

        self._apply_scope_snapshot(result)
        errors = result.get("errors", {})
        warning_count = len(errors) if isinstance(errors, dict) else 0
        if warning_count:
            self._last_action = f"Scope parameters loaded with {warning_count} warning(s)"
            for section, error in errors.items():
                self._append_log(f"Refresh warning [{section}]: {error}")
            suffix = f"parameters loaded with {warning_count} warning(s)"
        else:
            self._last_action = "Scope parameters loaded"
            suffix = "scope parameters loaded"

        self._connection_ok = True
        self._update_scope_control_enabled()
        self._update_status_strip()
        self.statusBar().showMessage(f"Connected: {self._last_idn} | {suffix}")

    def _ensure_scope_parameter_pages_built(self) -> None:
        """Create lazy cards before assigning values, without changing the selected page."""
        ensure_page = getattr(self, "_ensure_control_page_built", None)
        page_states = getattr(self, "_lazy_control_pages_built", ())
        if callable(ensure_page):
            for index in range(len(page_states)):
                ensure_page(index)

        if hasattr(self, "channel_config_channel") and not getattr(
            self, "_snapshot_channel_hook_installed", False
        ):
            self.channel_config_channel.currentTextChanged.connect(
                self._apply_cached_channel_configuration
            )
            self._snapshot_channel_hook_installed = True

        if hasattr(self, "reference_channel") and not getattr(
            self, "_snapshot_reference_hook_installed", False
        ):
            self.reference_channel.currentTextChanged.connect(
                self._apply_cached_reference_configuration
            )
            self._snapshot_reference_hook_installed = True

    def _apply_scope_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._scope_parameter_snapshot = snapshot

        labels = snapshot.get("labels", {})
        for channel, edit in getattr(self, "channel_labels", {}).items():
            edit.setText(str(labels.get(channel, "")))

        self._apply_cached_channel_configuration()
        self._apply_cached_reference_configuration()

        math = snapshot.get("math", {}) or {}
        if hasattr(self, "math_config_display"):
            self.math_config_display.setChecked(
                self._bool_from_scope_response(math.get("display", "0"))
            )
            self.math_config_define.setText(str(math.get("define", "")))
            self.math_config_scale.setText(str(math.get("scale", "")))
            self.math_config_position.setText(str(math.get("position", "")))

        self._apply_measurement_snapshot(snapshot.get("measurements", {}) or {})
        self._apply_trigger_snapshot(snapshot)
        self._apply_acquisition_snapshot(snapshot.get("acquisition", {}) or {})
        self._apply_display_snapshot(snapshot.get("display", {}) or {})

    def _apply_cached_channel_configuration(self, _text: str | None = None) -> None:
        snapshot = getattr(self, "_scope_parameter_snapshot", {})
        channels = snapshot.get("channels", {}) if isinstance(snapshot, dict) else {}
        if not hasattr(self, "channel_config_channel"):
            return
        try:
            channel = int(self.channel_config_channel.currentText())
        except ValueError:
            return
        config = channels.get(channel, {}) or {}
        self.channel_config_display.setChecked(
            self._bool_from_scope_response(config.get("display", "0"))
        )
        self.channel_config_scale.setText(str(config.get("scale", "")))
        self.channel_config_position.setText(str(config.get("position", "")))
        self.channel_config_offset.setText(str(config.get("offset", "")))
        self._set_combo_text(self.channel_config_coupling, str(config.get("coupling", "")))
        self._set_combo_text(self.channel_config_bandwidth, str(config.get("bandwidth", "")))
        self.channel_config_invert.setChecked(
            self._bool_from_scope_response(config.get("invert", "0"))
        )
        self.channel_config_probe_gain.setText(str(config.get("probe_gain", "")))

    def _apply_measurement_snapshot(self, measurements: dict[int, Any]) -> None:
        if not hasattr(self, "existing_measurements"):
            return
        for slot, setup in measurements.items():
            values = self._measurement_setup_to_dict(setup)
            row = self._measurement_row_for_slot(int(slot))
            self._set_measurement_table_row(row, values)

        if not hasattr(self, "measurement_slot"):
            return
        try:
            selected_slot = int(self.measurement_slot.currentText())
        except ValueError:
            return
        selected = measurements.get(selected_slot)
        if selected is None:
            self.measurement_value.clear()
            return
        values = self._measurement_setup_to_dict(selected)
        self._set_measurement_editor(
            slot=selected_slot,
            measurement_type=values.get("type", ""),
            source1=values.get("source1", "") or "CH1",
            source2=values.get("source2", ""),
        )
        self.measurement_value.setText(values.get("value", ""))

    def _apply_trigger_snapshot(self, snapshot: dict[str, Any]) -> None:
        trigger = snapshot.get("trigger", {}) or {}
        if hasattr(self, "edge_mode"):
            self._set_combo_text(self.edge_mode, str(trigger.get("mode", "")))
            self._set_combo_text(self.edge_source, str(trigger.get("source", "")))
            self._set_combo_text(self.edge_slope, str(trigger.get("slope", "")))
            self._set_combo_text(self.edge_coupling, str(trigger.get("coupling", "")))
            self.edge_level.setText(str(trigger.get("level", "")))

        source = str(trigger.get("source", "")).strip().upper()
        level = str(trigger.get("level", ""))
        if hasattr(self, "trigger_channel"):
            if source.startswith("CH") and source[2:].isdigit():
                self._set_combo_text(self.trigger_channel, source[2:])
            self.trigger_level.setText(level)
            self.trigger_readback.setText(level)

        if hasattr(self, "horizontal_position"):
            position = snapshot.get("horizontal_position")
            if position is None:
                self.horizontal_position.clear()
            else:
                try:
                    self.horizontal_position.setText(f"{float(position):g}")
                except (TypeError, ValueError):
                    self.horizontal_position.setText(str(position))

    def _apply_acquisition_snapshot(self, acquisition: dict[str, Any]) -> None:
        if not hasattr(self, "acquisition_mode"):
            return
        mode = str(acquisition.get("mode", ""))
        average_count = str(acquisition.get("average_count", ""))
        record_length = str(acquisition.get("record_length", ""))
        length_label = _record_length_display(record_length) if record_length else ""
        self._set_combo_text(self.acquisition_mode, mode)
        self._set_combo_text(self.acquisition_average_count, average_count)
        self._set_combo_text(self.acquisition_record_length, length_label)
        self._update_average_count_enabled()
        self._acquisition_state = (
            f"{mode or 'Unknown'}, {length_label or 'Unknown length'} pts"
        )

    def _apply_display_snapshot(self, display: dict[str, Any]) -> None:
        if not hasattr(self, "display_backlight"):
            return
        self.display_backlight.setText(str(display.get("backlight", "")))
        self.display_waveform_intensity.setText(str(display.get("waveform", "")))
        self.display_graticule_intensity.setText(str(display.get("graticule", "")))
        self._set_combo_text(self.display_persistence, str(display.get("persistence", "")))
        self.display_message_text.setText(str(display.get("message_text", "")))
        self.display_message_state.setChecked(
            self._bool_from_scope_response(display.get("message_state", "0"))
        )

    def _finish_scope_action_error(self, description: str, exc: BaseException) -> None:
        """Keep connection/initial-refresh errors non-modal; preserve other dialogs."""
        if description not in NON_MODAL_CONNECTION_ACTIONS:
            return super()._finish_scope_action_error(description, exc)

        error_text = str(exc).strip() or exc.__class__.__name__
        self._connection_ok = False
        self._operation_active = False
        if description == CONNECTION_TEST_DESCRIPTION:
            self._last_idn = f"Error: {error_text}"
            prefix = "Connection error"
        else:
            prefix = "Scope refresh error"
        self._last_action = f"{prefix}: {error_text}"
        self._append_log(f"ERROR: {error_text}")
        self._update_scope_control_enabled()
        self._update_status_strip()
        self.statusBar().showMessage(f"{prefix}: {error_text}")
        return None


__all__ = [
    "CONNECTION_TEST_DESCRIPTION",
    "NON_MODAL_CONNECTION_ACTIONS",
    "REFERENCE_SCOPE_ACTIONS",
    "SCOPE_REFRESH_DESCRIPTION",
    "QtScopeWindow",
]
