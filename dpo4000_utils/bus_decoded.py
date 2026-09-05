"""Decoded BUS event models and capability contract.

DPO4000 BUS decoder configuration is supported independently from decoded-event
export. Event extraction remains unavailable until a concrete programmer-manual
command path is verified against real DPO4000 firmware.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class BusDecodedEvent:
    """One normalized decoded serial/parallel BUS event.

    The field order is kept compatible with the Logger L6 public contract so
    existing callers may continue to construct events positionally as
    ``(bus, protocol, timestamp_s, event_type, fields, raw_text)``.
    """

    bus: int
    protocol: str
    timestamp_s: float | None
    event_type: str
    fields: Mapping[str, Any] = field(default_factory=dict)
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a plain serializable mapping for Logger/export integrations."""
        return asdict(self)


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
