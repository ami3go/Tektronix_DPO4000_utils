"""Instrument classes for Tektronix DPO4000-family oscilloscopes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .acquisition_modes import AcquisitionModeReadbackMixin
from .acquisition_state import AcquisitionStateMixin
from .bus import BusMixin, normalize_bus
from .bus_decoded import (
    DecodedBusCapability,
    DecodedBusEventsUnavailable,
    UNQUALIFIED_DECODED_BUS_CAPABILITY,
)
from .channels import ChannelMixin
from .connection import ConnectionMixin
from .control import ControlMixin
from .errors import DPOError, DPOSettingsError, is_transport_error, transport_exception
from .hardcopy import HardcopyMixin
from .reference import ReferenceMixin
from .settings import SettingsMixin
from .trigger import TriggerMixin
from .waveform import WaveformMixin, write_waveforms_csv


class DPO4000Scope(
    ConnectionMixin,
    SettingsMixin,
    HardcopyMixin,
    WaveformMixin,
    ChannelMixin,
    TriggerMixin,
    AcquisitionModeReadbackMixin,
    AcquisitionStateMixin,
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

    def save_all_channels_to_single_csv(
        self,
        filename: str | Path,
        **waveform_options: Any,
    ) -> Path:
        waveforms = self.read_enabled_waveforms(**waveform_options)
        return write_waveforms_csv(filename, waveforms)

    def restore_default_setup(self) -> str:
        instrument = self.ensure_connected()
        try:
            instrument.write("RECALL:SETUP FACTORY")
        except DPOError:
            raise
        except Exception as exc:
            if is_transport_error(exc):
                raise transport_exception(exc, "Restoring scope default setup") from exc
            raise DPOSettingsError(f"Could not restore scope default setup: {exc}") from exc
        return "Scope default setup restored"

    def get_decoded_bus_capability(self) -> DecodedBusCapability:
        """Return the explicit qualification state for decoded BUS event export."""
        return UNQUALIFIED_DECODED_BUS_CAPABILITY

    def supports_decoded_bus_events(self) -> bool:
        """Return whether decoded BUS transaction extraction is hardware-qualified."""
        capability = self.get_decoded_bus_capability()
        return bool(capability.supported and capability.qualified)

    def read_decoded_bus_events(self, bus: int | str):
        """Return structured decoded BUS events when a qualified backend exists."""
        valid_bus = normalize_bus(bus)
        capability = self.get_decoded_bus_capability()
        raise DecodedBusEventsUnavailable(
            f"Decoded BUS{valid_bus} event extraction is unavailable: {capability.reason}"
        )


class DPO4054(DPO4000Scope):
    """Compatibility class for existing DPO4054 scripts."""
