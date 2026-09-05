"""Decoded BUS event models and capability contract.

DPO4000 BUS decoder configuration is supported independently from decoded-event
export. Event extraction remains unavailable until a concrete programmer-manual
command path is verified against real DPO4000 firmware.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BusDecodedEvent:
    """One normalized decoded serial/parallel BUS event."""

    bus: int
    event_type: str
    timestamp_s: float | None = None
    value: str = ""
    raw: Any = None


@dataclass(frozen=True, slots=True)
class DecodedBusCapability:
    """Hardware-qualification state for decoded BUS transaction extraction."""

    supported: bool
    qualified: bool
    reason: str
    command_family: str | None = None


UNQUALIFIED_DECODED_BUS_CAPABILITY = DecodedBusCapability(
    supported=False,
    qualified=False,
    reason=(
        "Decoded BUS transaction extraction has no stock DPO4000 programmer-manual "
        "command path that has been qualified on the project DPO4054. Decoder setup "
        "and display support do not imply transaction-table export support."
    ),
)


class DecodedBusEventsUnavailable(RuntimeError):
    """Raised when decoded BUS transaction extraction is not hardware-qualified."""


__all__ = [
    "BusDecodedEvent",
    "DecodedBusCapability",
    "DecodedBusEventsUnavailable",
    "UNQUALIFIED_DECODED_BUS_CAPABILITY",
]
