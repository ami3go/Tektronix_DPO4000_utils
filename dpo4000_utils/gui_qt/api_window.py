"""API-only instrument adapter for the launched DPO4000 Desk application.

The existing Qt presentation stack remains responsible for widgets, layout,
preferences, status, and user interaction. Instrument-facing handlers call only
the public ``dpo4000_utils`` API and consume asynchronous action completions.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog

from ..control import (
    AcquisitionConfig,
    ChannelConfig,
    DisplayConfig,
    MathConfig,
    bool_from_scope_response,
    record_length_label,
)
from .titlebar_tabs_window import QtScopeWindow as UiQtScopeWindow

DEFAULT_RESTORE_TIMEOUT_MS = 60_000


def _record_length_display(value: object) -> str:
    """Format a driver record-length readback for the editable GUI combo."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return record_length_label(text)
    except (TypeError, ValueError):
        return text


class QtScopeWindow(UiQtScopeWindow):
    """DPO4000 Desk window using only public driver operations."""

    def test_connection(self) -> None:
        self._run_action(
            "Testing scope connection",
            lambda scope: scope.query_identity(),
            on_success=lambda result: self._message("Scope IDN", str(result)),
        )

    def _capture_image_to(self, path: Path, description: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        rearm = self.rearm_after_image.isChecked()
        trigger_channel = self._trigger_channel_or_none()

        def action(scope) -> str:
            saved_path = scope.save_image_path(path)
            if rearm:
                scope.rearm_trigger_after_image(trigger_channel=trigger_channel)
            return str(saved_path)

        def completed(result: object) -> None:
            if isinstance(result, str):
                self._last_image_path = Path(result)
                self._load_preview(self._last_image_path)

        self._run_action(description, action, on_success=completed)

    def save_csv(self) -> None:
        path = self._build_output_path("csv")
        if not self._confirm_or_cancel_overwrite(path):
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self._run_action(
            "Saving enabled channel waveforms to CSV",
            lambda scope: str(scope.save_all_channels_to_single_csv(path)),
            on_success=lambda result: self._message("CSV saved", str(result)),
        )

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

        def completed(result: object) -> None:
            if isinstance(result, dict):
                self._message(
                    "Settings restored",
                    f"Instrument: {result.get('instrument', 'Unknown')}",
                )

        self._run_action(
            "Restoring scope settings JSON",
            lambda scope: scope.apply_scope_settings(
                path,
                wait_complete=wait_opc,
                check_error=True,
                opc_timeout_ms=DEFAULT_RESTORE_TIMEOUT_MS,
            ),
            on_success=completed,
        )

    def apply_trigger_level(self) -> None:
        channel = self._selected_trigger_channel()
        level = self._parsed_trigger_level()
        set_source = self.trigger_set_source.isChecked()

        def action(scope):
            if set_source:
                scope.set_edge_trigger_source(channel)
            readback = scope.set_trigger_level(level, channel=channel, verify=True)
            scope.run_acquisition()
            return readback

        self._run_action(
            f"Setting trigger CH{channel} level to {level}",
            action,
            on_success=lambda result: self.trigger_readback.setText(str(result)),
        )

    # ------------------------------------------------------------------
    # Channel and MATH configuration
    # ------------------------------------------------------------------
    def read_channel_configuration(self) -> None:
        channel = self._selected_config_channel()

        def completed(result: object) -> None:
            if not isinstance(result, dict):
                return
            self.channel_config_display.setChecked(
                bool_from_scope_response(result.get("display", "0"))
            )
            self.channel_config_scale.setText(result.get("scale", ""))
            self.channel_config_position.setText(result.get("position", ""))
            self.channel_config_offset.setText(result.get("offset", ""))
            self._set_combo_text(self.channel_config_coupling, result.get("coupling", ""))
            self._set_combo_text(self.channel_config_bandwidth, result.get("bandwidth", ""))
            self.channel_config_invert.setChecked(
                bool_from_scope_response(result.get("invert", "0"))
            )
            self.channel_config_probe_gain.setText(result.get("probe_gain", ""))

        self._run_action(
            f"Reading CH{channel} configuration",
            lambda scope: scope.get_channel_configuration(channel),
            on_success=completed,
        )

    def apply_channel_configuration(self) -> None:
        channel = self._selected_config_channel()
        config = ChannelConfig(
            channel=channel,
            display=self.channel_config_display.isChecked(),
            scale=self.channel_config_scale.text().strip() or None,
            position=self.channel_config_position.text().strip() or None,
            offset=self.channel_config_offset.text().strip() or None,
            coupling=self.channel_config_coupling.currentText().strip() or None,
            bandwidth=self.channel_config_bandwidth.currentText().strip() or None,
            invert=self.channel_config_invert.isChecked(),
            probe_gain=self.channel_config_probe_gain.text().strip() or None,
        )
        self._run_action(
            f"Applying CH{channel} configuration",
            lambda scope: scope.configure_channel(config),
        )

    def read_math_configuration(self) -> None:
        def completed(result: object) -> None:
            if not isinstance(result, dict):
                return
            self.math_config_display.setChecked(
                bool_from_scope_response(result.get("display", "0"))
            )
            self.math_config_define.setText(result.get("define", ""))
            self.math_config_scale.setText(result.get("scale", ""))
            self.math_config_position.setText(result.get("position", ""))

        self._run_action(
            "Reading MATH configuration",
            lambda scope: scope.get_math_configuration(),
            on_success=completed,
        )

    def apply_math_configuration(self) -> None:
        config = MathConfig(
            display=self.math_config_display.isChecked(),
            define=self.math_config_define.text().strip() or None,
            scale=self.math_config_scale.text().strip() or None,
            position=self.math_config_position.text().strip() or None,
        )
        self._run_action(
            "Applying MATH configuration",
            lambda scope: scope.configure_math(config),
        )

    # ------------------------------------------------------------------
    # Acquisition configuration
    # ------------------------------------------------------------------
    def _apply_acquisition_readback(
        self,
        result: object,
        *,
        fallback_mode: str = "",
        fallback_average_count: str = "",
        fallback_record_length: str = "",
    ) -> None:
        if not isinstance(result, dict):
            return
        self._set_combo_text(self.acquisition_mode, result.get("mode", fallback_mode))
        average_count = result.get("average_count", fallback_average_count)
        if average_count:
            self._set_combo_text(self.acquisition_average_count, average_count)
        length_label = _record_length_display(
            result.get("record_length", fallback_record_length)
        )
        self._set_combo_text(self.acquisition_record_length, length_label)
        self._update_average_count_enabled()
        mode = self.acquisition_mode.currentText().strip() or "Unknown"
        length = self.acquisition_record_length.currentText().strip() or "Unknown length"
        self._acquisition_state = f"{mode}, {length} pts"
        self._update_status_strip()

    def read_acquisition_setup(self) -> None:
        self._run_action(
            "Reading acquisition setup",
            lambda scope: scope.get_acquisition_setup(),
            on_success=self._apply_acquisition_readback,
        )

    def apply_acquisition_setup(self) -> None:
        mode = self.acquisition_mode.currentText().strip().upper()
        average_count = self.acquisition_average_count.currentText().strip()
        record_length = self.acquisition_record_length.currentText().strip()
        config = AcquisitionConfig(
            mode=mode or None,
            average_count=average_count if mode == "AVERAGE" and average_count else None,
            record_length=record_length or None,
        )

        def action(scope):
            scope.configure_acquisition(config)
            return scope.get_acquisition_setup()

        self._run_action(
            "Applying acquisition setup",
            action,
            on_success=lambda result: self._apply_acquisition_readback(
                result,
                fallback_mode=mode,
                fallback_average_count=average_count,
                fallback_record_length=record_length,
            ),
        )

    # ------------------------------------------------------------------
    # Display configuration
    # ------------------------------------------------------------------
    def read_display_settings(self) -> None:
        def completed(result: object) -> None:
            if not isinstance(result, dict):
                return
            self.display_backlight.setText(result.get("backlight", ""))
            self.display_waveform_intensity.setText(result.get("waveform", ""))
            self.display_graticule_intensity.setText(result.get("graticule", ""))
            self._set_combo_text(self.display_persistence, result.get("persistence", ""))
            self.display_message_text.setText(result.get("message_text", ""))
            self.display_message_state.setChecked(
                bool_from_scope_response(result.get("message_state", "0"))
            )

        self._run_action(
            "Reading display settings",
            lambda scope: scope.get_display_settings(),
            on_success=completed,
        )

    def apply_display_settings(self) -> None:
        config = DisplayConfig(
            backlight=self.display_backlight.text().strip() or None,
            waveform=self.display_waveform_intensity.text().strip() or None,
            graticule=self.display_graticule_intensity.text().strip() or None,
            persistence=self.display_persistence.currentText().strip() or None,
            message_text=self.display_message_text.text().strip() or None,
            message_state=self.display_message_state.isChecked(),
        )
        self._run_action(
            "Applying display settings",
            lambda scope: scope.apply_display_settings(config),
        )

    def clear_display_message(self) -> None:
        def completed(_result: object) -> None:
            self.display_message_text.clear()
            self.display_message_state.setChecked(False)

        self._run_action(
            "Clearing display screen text",
            lambda scope: scope.clear_display_message(),
            on_success=completed,
        )

    # ------------------------------------------------------------------
    # Existing measurement management
    # ------------------------------------------------------------------
    @staticmethod
    def _measurement_setup_to_dict(setup) -> dict[str, str]:
        return {
            "slot": str(setup.slot),
            "state": str(setup.state),
            "type": str(setup.measurement_type),
            "source1": str(setup.source1),
            "source2": str(setup.source2),
            "value": str(setup.value),
        }

    def read_existing_measurements(self) -> None:
        def completed(result: object) -> None:
            if not isinstance(result, dict):
                return
            for slot, setup in result.items():
                values = self._measurement_setup_to_dict(setup)
                row = self._measurement_row_for_slot(int(slot))
                self._set_measurement_table_row(row, values)

        self._run_action(
            "Reading existing measurement setup",
            lambda scope: scope.get_all_measurement_setups(),
            on_success=completed,
        )

    def apply_selected_measurement_edit(self) -> None:
        if not self._guard_measurement_edit_mode():
            return
        slot = self._selected_existing_measurement_slot()
        config = self._selected_measurement_config_for_slot(slot)

        def action(scope):
            scope.add_measurement(config)
            return scope.get_measurement_setup(slot)

        def completed(result: object) -> None:
            if result is None:
                return
            row = self._measurement_row_for_slot(slot)
            self._set_measurement_table_row(row, self._measurement_setup_to_dict(result))

        self._run_action(
            f"Applying edit to MEAS{slot}",
            action,
            on_success=completed,
        )


__all__ = ["QtScopeWindow"]
