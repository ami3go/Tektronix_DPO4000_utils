"""GUI wrapper that delegates tab sections to extracted builder modules."""

from __future__ import annotations

from .channels_panel import build_channels_card
from .connection_panel import build_connection_card
from .preview_panel import build_image_preview
from .settings_panel import build_settings_card
from .trigger_panel import build_trigger_card
from .waveform_window import WaveformScopeGui


class SectionedScopeGui(WaveformScopeGui):
    """Scope GUI that uses extracted builders for individual UI sections."""

    def _build_image_preview(self, parent) -> None:
        """Build the screen preview through the extracted panel module."""
        build_image_preview(self, parent)

    def _build_connection_card(self, parent) -> None:
        """Build the Connection tab through the extracted panel module."""
        build_connection_card(self, parent)

    def _build_channels_card(self, parent) -> None:
        """Build the Channels tab through the extracted panel module."""
        build_channels_card(self, parent)

    def _build_trigger_card(self, parent) -> None:
        """Build the Trigger tab through the extracted panel module."""
        build_trigger_card(self, parent)

    def _build_settings_card(self, parent) -> None:
        """Build the Settings tab through the extracted panel module."""
        build_settings_card(self, parent)


__all__ = ["SectionedScopeGui"]
