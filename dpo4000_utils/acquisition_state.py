"""Public acquisition/trigger-state readback for DPO4000-family scopes.

The commands in this module are documented by the Tektronix MSO4000/DPO4000
Programmer Manual.  Keeping them in the reusable driver lets Automation wait for
single acquisitions without embedding SCPI in Qt code.
"""

from __future__ import annotations

from typing import Any

from .control import normalize_scope_response_text
from .io_policy import required_query

ACQUISITION_STATE_QUERY = "ACQUIRE:STATE?"
TRIGGER_STATE_QUERY = "TRIGGER:STATE?"
TRIGGER_STATES = ("ARMED", "AUTO", "READY", "SAVE", "TRIGGER")


def normalize_acquisition_state(response: Any) -> bool:
    """Normalize ACQUIRE:STATE? to True while the acquisition system is running."""
    token = normalize_scope_response_text(response).strip().upper()
    if token in {"1", "ON", "RUN"}:
        return True
    if token in {"0", "OFF", "STOP"}:
        return False
    raise ValueError(f"Unexpected ACQUIRE:STATE response: {response!r}.")


def normalize_trigger_state(response: Any) -> str:
    """Normalize the documented TRIGGER:STATE? state token."""
    token = normalize_scope_response_text(response).strip().upper()
    if token not in TRIGGER_STATES:
        raise ValueError(
            f"Unexpected TRIGGER:STATE response {response!r}; expected one of {TRIGGER_STATES}."
        )
    return token


class AcquisitionStateMixin:
    """High-level state queries used by automation and non-GUI clients."""

    def get_acquisition_state(self) -> bool:
        """Return True while ACQUIRE:STATE reports running/on."""
        response = required_query(
            self.ensure_connected(),
            ACQUISITION_STATE_QUERY,
            operation="Reading acquisition state",
        )
        return normalize_acquisition_state(response)

    def is_acquiring(self) -> bool:
        """Alias for :meth:`get_acquisition_state` with predicate semantics."""
        return self.get_acquisition_state()

    def get_trigger_state(self) -> str:
        """Return ARMED/AUTO/READY/SAVE/TRIGGER from TRIGGER:STATE?."""
        response = required_query(
            self.ensure_connected(),
            TRIGGER_STATE_QUERY,
            operation="Reading trigger state",
        )
        return normalize_trigger_state(response)


__all__ = [
    "ACQUISITION_STATE_QUERY",
    "TRIGGER_STATE_QUERY",
    "TRIGGER_STATES",
    "AcquisitionStateMixin",
    "normalize_acquisition_state",
    "normalize_trigger_state",
]
