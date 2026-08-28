"""Instrument classes for Tektronix DPO4000-family oscilloscopes."""

from __future__ import annotations

from pathlib import Path

from .channels import ChannelMixin
from .connection import ConnectionMixin, visaResourceAddr
from .control import ControlMixin
from .hardcopy import HardcopyMixin
from .reference import ReferenceMixin
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
    ControlMixin,
    ReferenceMixin,
):
    """Tektronix DPO4000-family oscilloscope helper."""

    def __init__(
        self,
        resource_name=visaResourceAddr,
        auto_connect=True,
        *,
        timeout_ms: int | None = None,
        read_termination: str | None = None,
        write_termination: str | None = None,
    ):
        """Initialize an oscilloscope object.

        :param resource_name: VISA resource name for the oscilloscope.
        :param auto_connect: If True, connect during initialization.
        :param timeout_ms: Optional VISA timeout applied before the first query.
        :param read_termination: Optional VISA read termination applied before IDN.
        :param write_termination: Optional VISA write termination applied before IDN.
        """
        self.resource_name = resource_name
        self.timeout_ms = timeout_ms
        self.read_termination = read_termination
        self.write_termination = write_termination
        self.rm = None
        self.scope = None
        self.channel_labels = {}
        self.settings_folder = Path("scope_settings")
        self.settings_folder.mkdir(parents=True, exist_ok=True)

        if auto_connect:
            self.connect()


class DPO4054(DPO4000Scope):
    """Compatibility class for existing DPO4054 scripts."""
