"""Instrument classes for Tektronix DPO4000-family oscilloscopes."""

from __future__ import annotations

from pathlib import Path

from .channels import ChannelMixin
from .connection import ConnectionMixin, visaResourceAddr
from .hardcopy import HardcopyMixin
from .settings import SettingsMixin
from .trigger import TriggerMixin
from .waveform import WaveformMixin


class DPO4000Scope(
    ConnectionMixin,
    SettingsMixin,
    HardcopyMixin,
    WaveformMixin,
    ChannelMixin,
    TriggerMixin,
):
    """Tektronix DPO4000-family oscilloscope helper."""

    def __init__(self, resource_name=visaResourceAddr, auto_connect=True):
        """
        Initialize oscilloscope object.

        :param resource_name: VISA resource name for the oscilloscope.
        :param auto_connect: If True, connect during initialization.
        """
        self.resource_name = resource_name
        self.rm = None
        self.scope = None
        self.channel_labels = {}
        self.settings_folder = Path("scope_settings")
        self.settings_folder.mkdir(parents=True, exist_ok=True)

        if auto_connect:
            self.connect()


class DPO4054(DPO4000Scope):
    """Compatibility class for existing DPO4054 scripts."""
