"""Public Tektronix DPO4000 Tkinter GUI class.

This module flattens the previous active wrapper stack into one public class.
The legacy monolithic base window still supplies the core Tk lifecycle and scope
operation methods, while this class wires in extracted panel builders, shared
CSV/image/settings helpers, and persistent preferences.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..control import MEASUREMENT_TYPES_BY_GROUP, MeasurementConfig
from ..hardcopy import save_screen_png
from ..settings import apply_scope_settings_file
from ..waveform import save_enabled_channels_to_single_csv
from .channels_panel import build_channels_card
from .clipboard import ClipboardError, copy_image_file_to_clipboard
from .config import FileNaming, build_output_path as build_config_output_path, resolve_output_folder, safe_filename_part
from .connection_panel import build_connection_card
from .connection_ui import (
    build_ethernet_resource,
    parse_timeout_ms,
    parse_trigger_channel,
    parse_trigger_level,
    selected_resource_name,
)
from .control_panel import CONTROL_TAB_TITLE, build_control_tab
from .image_preview import usable_preview_size
from .log_panel import build_log
from .main_window import DEFAULT_RESTORE_TIMEOUT_MS, ScopeGui as BaseScopeGui
from .preferences import GuiPreferences, load_preferences, save_preferences
from .preview_panel import build_image_preview
from .settings_panel import build_settings_card
from .trigger_panel import build_trigger_card


class ScopeGui(BaseScopeGui):
    """Main GUI application with extracted panels and shared helper paths."""

    def __init__(self, preferences_path: str | Path | None = None) -> None:
        self._preferences_path = Path(preferences_path) if preferences_path is not None else None
        self._preference_save_job: str | None = None
        self._loading_preferences = True
        self._preferences = load_preferences(self._preferences_path)

        super().__init__()

        self._apply_preferences(self._preferences)
        self._loading_preferences = False
        self._bind_preference_traces()
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

    # ------------------------------------------------------------------
    # Variables and extracted UI panels
    # ------------------------------------------------------------------
    def _build_variables(self) -> None:
        super()._build_variables()

        self.measurement_slot_var = tk.StringVar(value="1")
        self.measurement_group_var = tk.StringVar(value="Amplitude")
        self.measurement_type_var = tk.StringVar(value=MEASUREMENT_TYPES_BY_GROUP["Amplitude"][0])
        self.measurement_source1_var = tk.StringVar(value="CH1")
        self.measurement_source2_var = tk.StringVar(value="")
        self.measurement_value_var = tk.StringVar(value="")

        self.horizontal_position_var = tk.StringVar(value="0")

        self.control_trigger_mode_var = tk.StringVar(value="AUTO")
        self.control_trigger_source_var = tk.StringVar(value="CH1")
        self.control_trigger_slope_var = tk.StringVar(value="RISE")
        self.control_trigger_coupling_var = tk.StringVar(value="DC")
        self.control_trigger_level_var = tk.StringVar(value="1.0")

    def _build_control_tabs(self, parent: tk.Widget) -> None:
        """Build right-side tabs, including the extended Control tab."""
        notebook = ttk.Notebook(parent)
        notebook.grid(row=0, column=0, sticky="nsew")

        connection_tab = ttk.Frame(notebook, padding=8)
        channels_tab = ttk.Frame(notebook, padding=8)
        trigger_tab = ttk.Frame(notebook, padding=8)
        control_tab = ttk.Frame(notebook, padding=8)
        settings_tab = ttk.Frame(notebook, padding=8)
        log_tab = ttk.Frame(notebook, padding=8)

        notebook.add(connection_tab, text="Connection")
        notebook.add(channels_tab, text="Channels")
        notebook.add(trigger_tab, text="Trigger")
        notebook.add(control_tab, text=CONTROL_TAB_TITLE)
        notebook.add(settings_tab, text="Settings")
        notebook.add(log_tab, text="Log")

        self._build_connection_card(connection_tab)
        self._build_channels_card(channels_tab)
        self._build_trigger_card(trigger_tab)
        self._build_control_tab(control_tab)
        self._build_settings_card(settings_tab)
        self._build_log(log_tab)

    def _build_image_preview(self, parent) -> None:
        build_image_preview(self, parent)

    def _build_connection_card(self, parent) -> None:
        build_connection_card(self, parent)

    def _build_channels_card(self, parent) -> None:
        build_channels_card(self, parent)

    def _build_trigger_card(self, parent) -> None:
        build_trigger_card(self, parent)

    def _build_control_tab(self, parent) -> None:
        build_control_tab(self, parent)

    def _build_settings_card(self, parent) -> None:
        build_settings_card(self, parent)

    def _build_log(self, parent) -> None:
        build_log(self, parent)

    # ------------------------------------------------------------------
    # Extracted connection / validation helpers
    # ------------------------------------------------------------------
    def _ethernet_resource_name(self) -> str:
        return build_ethernet_resource(
            self.eth_host_var.get(),
            self.eth_protocol_var.get(),
            self.eth_port_var.get(),
        )

    def _selected_resource_name(self) -> str:
        resource = selected_resource_name(
            self.connection_mode_var.get(),
            self.resource_var.get(),
            self.eth_host_var.get(),
            self.eth_protocol_var.get(),
            self.eth_port_var.get(),
        )
        if self.connection_mode_var.get() == "ethernet":
            self.generated_resource_var.set(resource)
        return resource

    def _timeout_ms(self) -> int:
        return parse_timeout_ms(self.timeout_var.get())

    def _trigger_channel_or_none(self) -> int | None:
        return parse_trigger_channel(self.trigger_channel_var.get(), allow_empty=True)

    def _selected_trigger_channel(self) -> int:
        channel = parse_trigger_channel(self.trigger_setup_channel_var.get(), allow_empty=False)
        assert channel is not None
        return channel

    def _parsed_trigger_level(self) -> float | str:
        return parse_trigger_level(self.trigger_level_var.get())

    # ------------------------------------------------------------------
    # Extracted output path helpers
    # ------------------------------------------------------------------
    def _configured_output_folder(self, create: bool = True) -> Path:
        folder = resolve_output_folder(self.output_folder_var.get())
        if create:
            folder.mkdir(parents=True, exist_ok=True)
        self.output_folder = folder
        return folder

    @staticmethod
    def _safe_filename_part(text: str, fallback: str) -> str:
        return safe_filename_part(text, fallback)

    def _build_output_path(self, kind: str) -> Path:
        if kind == "png":
            naming = FileNaming(
                prefix=self.png_prefix_var.get(),
                base=self.png_base_var.get(),
                extension=".png",
                fallback="scope_screen",
                add_timestamp=bool(self.png_add_timestamp_var.get()),
            )
        elif kind == "csv":
            naming = FileNaming(
                prefix=self.csv_prefix_var.get(),
                base=self.csv_base_var.get(),
                extension=".csv",
                fallback="scope_waveform",
                add_timestamp=bool(self.csv_add_timestamp_var.get()),
            )
        elif kind == "settings":
            naming = FileNaming(
                prefix=self.settings_prefix_var.get(),
                base=self.settings_base_var.get(),
                extension=".json",
                fallback="dpo4054_setup",
                add_timestamp=bool(self.settings_add_timestamp_var.get()),
            )
        else:
            raise ValueError(f"Unknown output kind: {kind}")
        return build_config_output_path(self.output_folder_var.get(), naming)

    # ------------------------------------------------------------------
    # Extracted preview helpers
    # ------------------------------------------------------------------
    def _preview_area_size(self) -> tuple[int, int]:
        width = self.preview_label.winfo_width()
        height = self.preview_label.winfo_height()

        if width <= 10 or height <= 10:
            self.update_idletasks()
            width = self.preview_label.winfo_width()
            height = self.preview_label.winfo_height()

        size = usable_preview_size(width, height)
        return size.width, size.height

    def _load_preview(self, path: Path) -> None:
        """Load a captured image and focus the preview for Ctrl+C copy."""
        self._last_image_path = path
        self._render_preview_to_fit(path)
        try:
            self.preview_label.focus_set()
        except Exception:
            pass

    def copy_preview_to_clipboard(self, _event=None) -> str:
        """Copy the latest captured/saved preview PNG to the system clipboard."""
        path = self._last_image_path
        if path is None:
            message = "No preview image is available to copy. Capture or save a PNG first."
            self.status_var.set(message)
            self._append_log(message)
            return "break"

        try:
            copy_image_file_to_clipboard(path)
        except ClipboardError as exc:
            message = f"Could not copy preview image to clipboard: {exc}"
            self.status_var.set("Clipboard copy failed")
            self._append_log(message)
            messagebox.showerror("Copy preview", message)
            return "break"
        except Exception as exc:
            message = f"Unexpected clipboard error: {exc}"
            self.status_var.set("Clipboard copy failed")
            self._append_log(message)
            messagebox.showerror("Copy preview", message)
            return "break"

        message = f"Copied preview image to clipboard: {path}"
        self.status_var.set("Preview image copied to clipboard")
        self._append_log(message)
        return "break"

    # ------------------------------------------------------------------
    # Control tab actions
    # ------------------------------------------------------------------
    def _run_scope_control_job(
        self,
        description: str,
        operation: Callable[[object], object],
        ui_update: Callable[[object], None] | None = None,
    ) -> None:
        def job():
            def action(scope):
                return operation(scope)

            result = self._new_scope_session(action)
            if ui_update is not None:
                self.after(0, lambda: ui_update(result))
            return {"control_result": result}

        self._run_job(description, job)

    def _on_measurement_group_changed(self, _event=None) -> None:
        group = self.measurement_group_var.get()
        choices = MEASUREMENT_TYPES_BY_GROUP.get(group, ())
        if not choices:
            return
        self.measurement_type_var.set(choices[0])
        combo = getattr(self, "measurement_type_combo", None)
        if combo is not None:
            combo.configure(values=choices)

    def _selected_measurement_config(self) -> MeasurementConfig:
        return MeasurementConfig(
            slot=int(self.measurement_slot_var.get()),
            measurement_type=self.measurement_type_var.get(),
            source1=self.measurement_source1_var.get(),
            source2=self.measurement_source2_var.get().strip() or None,
        )

    def add_measurement_to_display(self) -> None:
        config = self._selected_measurement_config()

        def operation(scope):
            scope.add_measurement(config)
            return f"MEAS{config.slot} {config.measurement_type.upper()}"

        self._run_scope_control_job(
            f"Adding {config.measurement_type.upper()} measurement to MEAS{config.slot}",
            operation,
        )

    def read_measurement_value(self) -> None:
        slot = int(self.measurement_slot_var.get())

        def operation(scope):
            return scope.read_measurement_value(slot)

        self._run_scope_control_job(
            f"Reading MEAS{slot} value",
            operation,
            lambda value: self.measurement_value_var.set(str(value)),
        )

    def clear_measurement_slot(self) -> None:
        slot = int(self.measurement_slot_var.get())

        def operation(scope):
            scope.disable_measurement(slot)
            return f"MEAS{slot} disabled"

        self._run_scope_control_job(f"Clearing MEAS{slot}", operation)

    def clear_all_measurements(self) -> None:
        def operation(scope):
            scope.disable_all_measurements()
            return "All measurement slots disabled"

        self._run_scope_control_job("Clearing all measurement slots", operation)

    def set_horizontal_position(self) -> None:
        position = self.horizontal_position_var.get()

        def operation(scope):
            scope.set_horizontal_position(position)
            return position

        self._run_scope_control_job(f"Setting horizontal position to {position}", operation)

    def read_horizontal_position(self) -> None:
        self._run_scope_control_job(
            "Reading horizontal position",
            lambda scope: scope.get_horizontal_position(),
            lambda value: self.horizontal_position_var.set(f"{float(value):g}"),
        )

    def nudge_horizontal_position(self, delta: int | float) -> None:
        self._run_scope_control_job(
            f"Nudging horizontal position by {delta:g}",
            lambda scope: scope.nudge_horizontal_position(delta),
            lambda value: self.horizontal_position_var.set(f"{float(value):g}"),
        )

    def set_horizontal_position_to_zero(self) -> None:
        self.horizontal_position_var.set("0")
        self.set_horizontal_position()

    def apply_edge_trigger_controls(self) -> None:
        source = self.control_trigger_source_var.get()
        slope = self.control_trigger_slope_var.get()
        coupling = self.control_trigger_coupling_var.get()
        mode = self.control_trigger_mode_var.get()
        level = self.control_trigger_level_var.get()

        def operation(scope):
            scope.configure_edge_trigger(
                source=source,
                slope=slope,
                coupling=coupling,
                mode=mode,
                level=level,
            )
            return f"{mode} edge trigger on {source}"

        self._run_scope_control_job("Applying edge trigger setup", operation)

    def run_acquisition(self) -> None:
        self._run_scope_control_job("Starting acquisition", lambda scope: scope.run_acquisition())

    def stop_acquisition(self) -> None:
        self._run_scope_control_job("Stopping acquisition", lambda scope: scope.stop_acquisition())

    def single_acquisition(self) -> None:
        self._run_scope_control_job("Starting single acquisition", lambda scope: scope.single_acquisition())

    def continuous_acquisition(self) -> None:
        self._run_scope_control_job("Returning acquisition to continuous mode", lambda scope: scope.continuous_acquisition())

    def force_trigger_event(self) -> None:
        self._run_scope_control_job("Forcing trigger event", lambda scope: scope.force_trigger_event())

    # ------------------------------------------------------------------
    # Shared hardcopy / settings / waveform paths
    # ------------------------------------------------------------------
    @staticmethod
    def _save_scope_image_png_robust(scope, path: Path) -> Path:
        return save_screen_png(getattr(scope, "scope", None), path)

    def restore_settings(self) -> None:
        selected = filedialog.askopenfilename(
            title="Restore scope settings JSON",
            initialdir=str(self._configured_output_folder(create=True)),
            filetypes=[("JSON file", "*.json"), ("All files", "*.*")],
        )
        if not selected:
            return

        path = Path(selected)
        wait_opc = self.restore_wait_opc_var.get()

        def job():
            def action(scope):
                return apply_scope_settings_file(
                    getattr(scope, "scope", None),
                    path,
                    wait_complete=wait_opc,
                    check_error=True,
                    opc_timeout_ms=DEFAULT_RESTORE_TIMEOUT_MS,
                )

            data = self._new_scope_session(action)
            instrument = data.get("instrument", "Unknown") if isinstance(data, dict) else "Unknown"
            return {"instrument": instrument}

        self._run_job("Restoring scope settings JSON", job)

    @staticmethod
    def _apply_scope_settings_locally(
        scope,
        file_path: Path,
        wait_complete: bool = False,
        check_error: bool = True,
        restore_delay_s: float = 2.0,
        opc_timeout_ms: int = DEFAULT_RESTORE_TIMEOUT_MS,
    ) -> dict:
        return apply_scope_settings_file(
            getattr(scope, "scope", None),
            file_path,
            wait_complete=wait_complete,
            check_error=check_error,
            restore_delay_s=restore_delay_s,
            opc_timeout_ms=opc_timeout_ms,
        )

    def save_csv(self) -> None:
        path = self._build_output_path("csv")
        if not self._confirm_or_cancel_overwrite(path):
            return
        path.parent.mkdir(parents=True, exist_ok=True)

        def job():
            def action(scope):
                return str(save_enabled_channels_to_single_csv(getattr(scope, "scope", None), path))

            saved = self._new_scope_session(action)
            return {"saved_path": saved}

        self._run_job("Saving enabled channel waveforms to CSV", job)

    # ------------------------------------------------------------------
    # Preference persistence
    # ------------------------------------------------------------------
    def _preference_variables(self) -> Iterable[tk.Variable]:
        return (
            self.connection_mode_var,
            self.resource_var,
            self.eth_host_var,
            self.eth_port_var,
            self.eth_protocol_var,
            self.timeout_var,
            self.output_folder_var,
            self.png_prefix_var,
            self.png_base_var,
            self.png_add_timestamp_var,
            self.csv_prefix_var,
            self.csv_base_var,
            self.csv_add_timestamp_var,
            self.settings_prefix_var,
            self.settings_base_var,
            self.settings_add_timestamp_var,
            self.restore_wait_opc_var,
            self.rearm_after_image_var,
            self.trigger_channel_var,
            self.trigger_setup_channel_var,
            self.trigger_level_var,
            self.trigger_set_source_var,
        )

    def _bind_preference_traces(self) -> None:
        for variable in self._preference_variables():
            variable.trace_add("write", self._schedule_preference_save)

    def _apply_preferences(self, preferences: GuiPreferences) -> None:
        self.connection_mode_var.set(preferences.connection_mode)
        self.resource_var.set(preferences.visa_resource)
        self.eth_host_var.set(preferences.ethernet_host)
        self.eth_port_var.set(preferences.ethernet_port)
        self.eth_protocol_var.set(preferences.ethernet_protocol)
        self.timeout_var.set(preferences.timeout_ms)
        self.output_folder_var.set(preferences.output_folder)
        self.png_prefix_var.set(preferences.png_prefix)
        self.png_base_var.set(preferences.png_base)
        self.png_add_timestamp_var.set(preferences.png_add_timestamp)
        self.csv_prefix_var.set(preferences.csv_prefix)
        self.csv_base_var.set(preferences.csv_base)
        self.csv_add_timestamp_var.set(preferences.csv_add_timestamp)
        self.settings_prefix_var.set(preferences.settings_prefix)
        self.settings_base_var.set(preferences.settings_base)
        self.settings_add_timestamp_var.set(preferences.settings_add_timestamp)
        self.restore_wait_opc_var.set(preferences.restore_wait_opc)
        self.rearm_after_image_var.set(preferences.rearm_after_image)
        self.trigger_channel_var.set(preferences.trigger_channel_after_image)
        self.trigger_setup_channel_var.set(preferences.trigger_setup_channel)
        self.trigger_level_var.set(preferences.trigger_level)
        self.trigger_set_source_var.set(preferences.trigger_set_source)

        self.output_folder = self._configured_output_folder(create=False)
        self._refresh_generated_ethernet_resource()
        self._update_visa_resource_list((preferences.visa_resource,))

    def _collect_preferences(self) -> GuiPreferences:
        return GuiPreferences(
            connection_mode=self.connection_mode_var.get(),
            visa_resource=self.resource_var.get(),
            ethernet_host=self.eth_host_var.get(),
            ethernet_port=self.eth_port_var.get(),
            ethernet_protocol=self.eth_protocol_var.get(),
            timeout_ms=self.timeout_var.get(),
            output_folder=self.output_folder_var.get(),
            png_prefix=self.png_prefix_var.get(),
            png_base=self.png_base_var.get(),
            png_add_timestamp=bool(self.png_add_timestamp_var.get()),
            csv_prefix=self.csv_prefix_var.get(),
            csv_base=self.csv_base_var.get(),
            csv_add_timestamp=bool(self.csv_add_timestamp_var.get()),
            settings_prefix=self.settings_prefix_var.get(),
            settings_base=self.settings_base_var.get(),
            settings_add_timestamp=bool(self.settings_add_timestamp_var.get()),
            restore_wait_opc=bool(self.restore_wait_opc_var.get()),
            rearm_after_image=bool(self.rearm_after_image_var.get()),
            trigger_channel_after_image=self.trigger_channel_var.get(),
            trigger_setup_channel=self.trigger_setup_channel_var.get(),
            trigger_level=self.trigger_level_var.get(),
            trigger_set_source=bool(self.trigger_set_source_var.get()),
        )

    def _refresh_generated_ethernet_resource(self) -> None:
        if not self.eth_host_var.get().strip():
            self.generated_resource_var.set("")
            return
        try:
            self.generated_resource_var.set(self._ethernet_resource_name())
        except Exception:
            self.generated_resource_var.set("")

    def _schedule_preference_save(self, *_args: object) -> None:
        if self._loading_preferences:
            return
        if self._preference_save_job is not None:
            try:
                self.after_cancel(self._preference_save_job)
            except Exception:
                pass
        self._preference_save_job = self.after(700, self._save_preferences_safely)

    def _save_preferences_safely(self) -> Path | None:
        self._preference_save_job = None
        try:
            path = save_preferences(self._collect_preferences(), self._preferences_path)
        except Exception as exc:
            try:
                self._append_log(f"Could not save GUI preferences: {exc}")
            except Exception:
                pass
            return None
        return path

    def _on_window_close(self) -> None:
        if self._preference_save_job is not None:
            try:
                self.after_cancel(self._preference_save_job)
            except Exception:
                pass
            self._preference_save_job = None
        self._save_preferences_safely()
        self.destroy()


__all__ = ["ScopeGui"]
