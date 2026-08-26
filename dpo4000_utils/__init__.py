"""Tektronix DPO4000 utility package."""

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
from .hardcopy import extract_png_bytes, strip_ieee_block_header
from .instrument import DPO4000Scope, DPO4054
from .session import scope_session
from .waveform import parse_ascii_curve

__all__ = [
    "AcquisitionConfig",
    "ChannelConfig",
    "DPO4000Scope",
    "DPO4054",
    "DisplayConfig",
    "MathConfig",
    "MeasurementConfig",
    "MeasurementSetup",
    "visaResourceAddr",
    "build_tcpip_instr_resource",
    "build_tcpip_socket_resource",
    "list_visa_resources",
    "scope_session",
    "extract_png_bytes",
    "strip_ieee_block_header",
    "parse_ascii_curve",
]
