"""Tektronix DPO4000 utility package."""

from .bus import BusConfig
from .connection import (
    build_tcpip_instr_resource,
    build_tcpip_socket_resource,
    list_visa_resources,
    visaResourceAddr,
)
from .control import (
    AcquisitionConfig,
    ChannelConfig,
    DisplayConfig,
    MathConfig,
    MeasurementConfig,
    MeasurementSetup,
)
from .errors import (
    DPOCleanupError,
    DPOConnectionError,
    DPOError,
    DPOImageCaptureError,
    DPONotConnectedError,
    DPOProtocolError,
    DPOSettingsError,
    DPOTimeoutError,
    DPOTransportError,
    DPOWaveformError,
)
from .hardcopy import extract_png_bytes, strip_ieee_block_header
from .reference import ReferenceConfig
from .instrument import DPO4000Scope, DPO4054
from .session import scope_session
from .waveform import (
    WaveformData,
    WaveformPreamble,
    WaveformRequest,
    parse_ascii_curve,
    read_channel_waveform_data,
    read_waveform,
)

__all__ = [
    "AcquisitionConfig",
    "BusConfig",
    "ChannelConfig",
    "DPO4000Scope",
    "DPO4054",
    "DPOCleanupError",
    "DPOConnectionError",
    "DPOError",
    "DPOImageCaptureError",
    "DPONotConnectedError",
    "DPOProtocolError",
    "DPOSettingsError",
    "DPOTimeoutError",
    "DPOTransportError",
    "DPOWaveformError",
    "DisplayConfig",
    "MathConfig",
    "MeasurementConfig",
    "MeasurementSetup",
    "ReferenceConfig",
    "WaveformData",
    "WaveformPreamble",
    "WaveformRequest",
    "visaResourceAddr",
    "build_tcpip_instr_resource",
    "build_tcpip_socket_resource",
    "list_visa_resources",
    "scope_session",
    "extract_png_bytes",
    "strip_ieee_block_header",
    "parse_ascii_curve",
    "read_channel_waveform_data",
    "read_waveform",
]
