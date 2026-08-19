"""GUI wrapper that delegates tab sections to extracted builder modules."""

from __future__ import annotations

from .connection_panel import build_connection_card
from .waveform_window import WaveformScopeGui


class SectionedScopeGui(WaveformScopeGui):
    """Scope GUI that uses extracted builders for individual UI sections."""

    def _build_connection_card(self, parent) -> None:
        """Build the Connection tab through the extracted panel module."""
        build_connection_card(self, parent)


__all__ = ["SectionedScopeGui"]
