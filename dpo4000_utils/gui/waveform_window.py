"""Waveform-aware GUI wrapper.

This module routes GUI CSV export through the shared driver waveform helpers
without editing the large Tkinter main-window implementation.
"""

from __future__ import annotations

from ..waveform import save_enabled_channels_to_single_csv
from .stateful_window import PersistentScopeGui


class WaveformScopeGui(PersistentScopeGui):
    """Scope GUI that uses shared waveform helpers for CSV export."""

    def save_csv(self) -> None:
        """Save enabled channel waveforms through the shared waveform helper."""
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


__all__ = ["WaveformScopeGui"]
