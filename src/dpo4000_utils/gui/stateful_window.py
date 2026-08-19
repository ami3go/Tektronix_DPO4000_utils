"""Persistent GUI window wrapper.

This module wires the pure ``preferences`` helpers into the existing Tkinter
``ScopeGui`` implementation without editing the large main window class directly.
It keeps the behavior low-risk: the old window still provides all widgets and
actions, while this wrapper only loads and saves user-facing UI state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import tkinter as tk

from .main_window import ScopeGui as BaseScopeGui
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
