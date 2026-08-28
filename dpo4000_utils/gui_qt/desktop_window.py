"""Final desktop presentation policy for DPO4000 Desk.

This layer specializes the API-only Qt window with non-modal connection feedback
and a post-connection state refresh.  Instrument reads are collected through the
public driver API in one session and then projected into the already-built Qt
cards.
"""

from __future__ import annotations

from typing import Any

from ..scope_snapshot import read_scope_snapshot
from .api_window import QtScopeWindow as ApiQtScopeWindow, _record_length_display

CONNECTION_TEST_DESCRIPTION = "Testing scope connection"
SCOPE_REFRESH_DESCRIPTION = "Reading scope parameters"
NON_MODAL_CONNECTION_ACTIONS = {CONNECTION_TEST_DESCRIPTION, SCOPE_REFRESH_DESCRIPTION}


class QtScopeWindow(ApiQtScopeWindow):
    """Launched desktop window with status-only connection feedback."""

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

    def _apply_scope_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._scope_parameter_snapshot = snapshot

        labels = snapshot.get("labels", {})
        for channel, edit in getattr(self, "channel_labels", {}).items():
            edit.setText(str(labels.get(channel, "")))

        self._apply_cached_channel_configuration()

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
    "SCOPE_REFRESH_DESCRIPTION",
    "QtScopeWindow",
]
