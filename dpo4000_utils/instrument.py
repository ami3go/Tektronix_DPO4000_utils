"""Instrument classes for Tektronix DPO4000-family oscilloscopes."""

from __future__ import annotations

from pathlib import Path

from .bus import BusMixin
from .channels import ChannelMixin
from .connection import ConnectionMixin
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
    BusMixin,
):
    """Tektronix DPO4000-family oscilloscope helper."""

    def __init__(
        self,
        resource_name: str | None = None,
        auto_connect: bool = False,
        *,
        timeout_ms: int | None = None,
        read_termination: str | None = None,
        write_termination: str | None = None,
        settings_folder: str | Path = "scope_settings",
    ):
        """Initialize an oscilloscope object without implicit I/O.

        :param resource_name: Explicit VISA resource name. The reusable driver no
            longer assumes one physical scope serial number.
        :param auto_connect: If True, connect during initialization. Defaults to
            False so construction is side-effect free.
        :param timeout_ms: Optional VISA timeout applied before the first query.
        :param read_termination: Optional VISA read termination applied before IDN.
        :param write_termination: Optional VISA write termination applied before IDN.
        :param settings_folder: Default folder used only when a settings save/restore
            operation actually needs it. Construction does not create the folder.
        """
        self.resource_name = resource_name
        self.timeout_ms = timeout_ms
        self.read_termination = read_termination
        self.write_termination = write_termination
        self.rm = None
        self.scope = None
        self.channel_labels: dict[int, str] = {}
        self.settings_folder = Path(settings_folder)

        if auto_connect:
            self.connect()


class DPO4054(DPO4000Scope):
    """Compatibility class for existing DPO4054 scripts."""
