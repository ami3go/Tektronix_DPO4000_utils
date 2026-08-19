"""Persistent GUI window wrapper.

This module wires the pure ``preferences`` helpers into the existing Tkinter
``ScopeGui`` implementation without editing the large main window class directly.
It keeps the behavior low-risk: the old window still provides all widgets and
actions, while this wrapper loads/saves user-facing UI state and delegates small
validation/path calculations to testable helper modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import tkinter as tk
from tkinter import filedialog

from ..hardcopy import save_screen_png
from ..settings import apply_scope_settings_file
from .config import FileNaming, build_output_path as build_config_output_path, resolve_output_folder, safe_filename_part
from .connection_ui import (
    build_ethernet_resource,
    parse_timeout_ms,
    parse_trigger_channel,
    parse_trigger_level,
    selected_resource_name,
)
from .image_preview import usable_preview_size
from .main_window import DEFAULT_RESTORE_TIMEOUT_MS, ScopeGui as BaseScopeGui
from .preferences import GuiPreferences, load_preferences, save_preferences


class PersistentScopeGui(BaseScopeGui):
    """Scope GUI with persisted user preferences.

    Preferences are loaded after the base window has created its Tk variables and
    widgets. They are saved on close and also debounced after user edits to the
    relevant controls.
    """

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
    # Extracted connection / validation helpers
    # ------------------------------------------------------------------
    def _ethernet_resource_name(self) -> str:
        """Build a VISA TCPIP resource string from the Ethernet fields."""
        return build_ethernet_resource(
            self.eth_host_var.get(),
            self.eth_protocol_var.get(),
            self.eth_port_var.get(),
        )

    def _selected_resource_name(self) -> str:
        """Return the resource that should be used for the next operation."""
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
        """Return the validated VISA timeout in milliseconds."""
        return parse_timeout_ms(self.timeout_var.get())

    def _trigger_channel_or_none(self) -> int | None:
        """Return optional post-image trigger channel."""
        return parse_trigger_channel(self.trigger_channel_var.get(), allow_empty=True)

    def _selected_trigger_channel(self) -> int:
        """Return selected trigger setup channel."""
        channel = parse_trigger_channel(self.trigger_setup_channel_var.get(), allow_empty=False)
        assert channel is not None
        return channel

    def _parsed_trigger_level(self) -> float | str:
        """Return numeric volts or supported Tektronix trigger preset."""
        return parse_trigger_level(self.trigger_level_var.get())

    # ------------------------------------------------------------------
    # Extracted output path helpers
    # ------------------------------------------------------------------
    def _configured_output_folder(self, create: bool = True) -> Path:
        """Return the configured output folder as an absolute Path."""
        folder = resolve_output_folder(self.output_folder_var.get())
        if create:
            folder.mkdir(parents=True, exist_ok=True)
        self.output_folder = folder
        return folder

    @staticmethod
    def _safe_filename_part(text: str, fallback: str) -> str:
        """Return a filesystem-safe filename part for Windows/Linux."""
        return safe_filename_part(text, fallback)

    def _build_output_path(self, kind: str) -> Path:
        """Build output filename from Settings tab options."""
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
    # Extracted preview sizing helper
    # ------------------------------------------------------------------
    def _preview_area_size(self) -> tuple[int, int]:
        """Return useful preview area size in pixels."""
        width = self.preview_label.winfo_width()
        height = self.preview_label.winfo_height()

        if width <= 10 or height <= 10:
            self.update_idletasks()
            width = self.preview_label.winfo_width()
            height = self.preview_label.winfo_height()

        size = usable_preview_size(width, height)
        return size.width, size.height

    # ------------------------------------------------------------------
    # Extracted hardcopy capture helper
    # ------------------------------------------------------------------
    @staticmethod
    def _save_scope_image_png_robust(scope, path: Path) -> Path:
        """Save a scope screenshot using the shared driver hardcopy helper."""
        return save_screen_png(getattr(scope, "scope", None), path)

    # ------------------------------------------------------------------
    # Extracted settings restore helper
    # ------------------------------------------------------------------
    def restore_settings(self) -> None:
        """Restore scope settings through the shared driver settings helper."""
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
        """Compatibility fallback that also uses the shared settings helper."""
        return apply_scope_settings_file(
            getattr(scope, "scope", None),
            file_path,
            wait_complete=wait_complete,
            check_error=check_error,
            restore_delay_s=restore_delay_s,
            opc_timeout_ms=opc_timeout_ms,
        )

    # ------------------------------------------------------------------
    # Preference persistence
    # ------------------------------------------------------------------
    def _preference_variables(self) -> Iterable[tk.Variable]:
        """Return Tk variables that should trigger preference autosave."""
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
        """Autosave preferences when the user edits persistent controls."""
        for variable in self._preference_variables():
            variable.trace_add("write", self._schedule_preference_save)

    def _apply_preferences(self, preferences: GuiPreferences) -> None:
        """Copy loaded preferences into existing Tk variables."""
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
        """Read current Tk variables into a serializable preferences object."""
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
        """Best-effort update of the readonly generated Ethernet resource field."""
        if not self.eth_host_var.get().strip():
            self.generated_resource_var.set("")
            return
        try:
            self.generated_resource_var.set(self._ethernet_resource_name())
        except Exception:
            self.generated_resource_var.set("")

    def _schedule_preference_save(self, *_args: object) -> None:
        """Debounce preference writes so typing does not write every character."""
        if self._loading_preferences:
            return
        if self._preference_save_job is not None:
            try:
                self.after_cancel(self._preference_save_job)
            except Exception:
                pass
        self._preference_save_job = self.after(700, self._save_preferences_safely)

    def _save_preferences_safely(self) -> Path | None:
        """Save preferences without interrupting the GUI if disk write fails."""
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
        """Save preferences once more before closing the GUI."""
        if self._preference_save_job is not None:
            try:
                self.after_cancel(self._preference_save_job)
            except Exception:
                pass
            self._preference_save_job = None
        self._save_preferences_safely()
        self.destroy()


__all__ = ["PersistentScopeGui"]
