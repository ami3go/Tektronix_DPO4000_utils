"""API-only adapter for the launched Tkinter DPO4000 GUI.

The widget/layout implementation is inherited from the existing GUI classes, but
all instrument actions in this launched adapter go through public
``dpo4000_utils`` APIs.  No GUI code in this module accesses ``scope.scope`` or
implements SCPI/hardcopy/settings transfer logic.
"""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

from ..connection import list_visa_resources
from ..session import scope_session
from .main_window import DEFAULT_RESTORE_TIMEOUT_MS
from .scope_gui import ScopeGui as UiScopeGui


class ScopeGui(UiScopeGui):
    """Tkinter GUI whose instrument boundary is the public DPO4000 API."""

    def _new_scope_session(self, action):
        """Run ``action(scope)`` in a short-lived driver-owned session."""
        with scope_session(
            self._selected_resource_name(),
            timeout_ms=self._timeout_ms(),
        ) as scope:
            return action(scope)

    def test_connection(self) -> None:
        def job():
            identity = self._new_scope_session(lambda scope: scope.query_identity())
            return {"labels": {}, "idn": identity}

        self._run_job("Testing scope connection", job)

    def list_visa_resources(self) -> None:
        def job():
            resources = list_visa_resources()
            if resources:
                text = "VISA resources found:\n" + "\n".join(resources)
            else:
                text = "No VISA resources found."
            self.after(0, lambda: messagebox.showinfo(self.title(), text))
            return {"visa_resources": resources}

        self._run_job("Refreshing VISA resource list", job)

    def read_trigger_level(self) -> None:
        channel = self._selected_trigger_channel()

        def job():
            level = self._new_scope_session(
                lambda scope: scope.get_trigger_level(channel=channel)
            )
            return {"trigger_level": level}

        self._run_job(f"Reading trigger level for CH{channel}", job)

    def apply_trigger_level(self) -> None:
        channel = self._selected_trigger_channel()
        level = self._parsed_trigger_level()
        set_source = bool(self.trigger_set_source_var.get())

        def action(scope):
            if set_source:
                scope.set_edge_trigger_source(channel)
            readback = scope.set_trigger_level(level, channel=channel, verify=True)
            scope.run_acquisition()
            return readback

        def job():
            readback = self._new_scope_session(action)
            return {"trigger_level": readback}

        self._run_job(f"Setting trigger CH{channel} level to {level}", job)

    def _capture_image_to(self, path: Path, description: str) -> None:
        """Capture through ``DPO4000Scope.save_image_path`` and update preview."""
        path.parent.mkdir(parents=True, exist_ok=True)
        rearm = bool(self.rearm_after_image_var.get())
        trigger_channel = self._trigger_channel_or_none()

        def action(scope):
            saved_path = scope.save_image_path(path)
            if rearm:
                scope.rearm_trigger_after_image(trigger_channel=trigger_channel)
            return str(saved_path)

        def job():
            saved = self._new_scope_session(action)
            return {"preview_path": saved}

        self._run_job(description, job)

    def save_csv(self) -> None:
        path = self._build_output_path("csv")
        if not self._confirm_or_cancel_overwrite(path):
            return
        path.parent.mkdir(parents=True, exist_ok=True)

        def job():
            saved = self._new_scope_session(
                lambda scope: str(scope.save_all_channels_to_single_csv(path))
            )
            return {"saved_path": saved}

        self._run_job("Saving enabled channel waveforms to CSV", job)

    def restore_settings(self) -> None:
        selected = filedialog.askopenfilename(
            title="Restore scope settings JSON",
            initialdir=str(self._configured_output_folder(create=True)),
            filetypes=[("JSON file", "*.json"), ("All files", "*.*")],
        )
        if not selected:
            return

        path = Path(selected)
        wait_opc = bool(self.restore_wait_opc_var.get())

        def action(scope):
            return scope.apply_scope_settings(
                path,
                wait_complete=wait_opc,
                check_error=True,
                opc_timeout_ms=DEFAULT_RESTORE_TIMEOUT_MS,
            )

        def job():
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
        """Compatibility hook that delegates to the public driver method."""
        return scope.apply_scope_settings(
            file_path,
            wait_complete=wait_complete,
            check_error=check_error,
            restore_delay_s=restore_delay_s,
            opc_timeout_ms=opc_timeout_ms,
        )


__all__ = ["ScopeGui"]
