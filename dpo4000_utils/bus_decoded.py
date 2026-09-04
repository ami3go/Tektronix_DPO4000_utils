"""Structured decoded-BUS event contract for Logger integrations.

The DPO4000 configuration API is qualified, but decoded transaction-table extraction
has not yet been hardware-qualified. The public contract is provided now so the
Logger can remain protocol-independent without inventing an undocumented command.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class BusDecodedEvent:
    bus: int
    protocol: str
    timestamp_s: float | None
    event_type: str
    fields: Mapping[str, Any] = field(default_factory=dict)
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DecodedBusEventsUnavailable(NotImplementedError):
    """Raised when decoded transaction extraction is not qualified for this driver."""


__all__ = ["BusDecodedEvent", "DecodedBusEventsUnavailable"]
